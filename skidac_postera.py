import os
import re
from io import BytesIO
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
import requests
from PIL import Image


APP_DIR = os.path.dirname(os.path.abspath(__file__))
POSTERI_DIR = os.path.join(APP_DIR, "posteri")
TMDB_KLJUC_FAJL = os.path.join(APP_DIR, "tmdb_kljuc.txt")
TMDB_PRETRAGA_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SLIKA_URL = "https://image.tmdb.org/t/p/w500"

os.makedirs(POSTERI_DIR, exist_ok=True)


def napravi_ime_fajla(tekst):
    tekst = tekst.lower().strip()
    tekst = re.sub(r"\bposter\b", "", tekst)
    tekst = re.sub(r"\bmovie\b", "", tekst)
    tekst = re.sub(r"\bfilm\b", "", tekst)
    tekst = re.sub(r"\b(19|20)\d{2}\b", "", tekst)
    tekst = re.sub(r"[^a-z0-9]+", "_", tekst)
    tekst = tekst.strip("_")
    return tekst or "poster"


def ocisti_upit(tekst):
    tekst = tekst.strip()
    tekst = re.sub(r"\s+", " ", tekst)
    return tekst.strip()


def ucitaj_tmdb_kljuc():
    if not os.path.exists(TMDB_KLJUC_FAJL):
        raise RuntimeError("Nedostaje fajl tmdb_kljuc.txt u folderu aplikacije.")

    with open(TMDB_KLJUC_FAJL, "r", encoding="utf-8") as fajl:
        kljuc = fajl.read().strip()

    if not kljuc:
        raise RuntimeError("Fajl tmdb_kljuc.txt je prazan.")

    return kljuc


def tmdb_get(url, params):
    kljuc = ucitaj_tmdb_kljuc()
    headers = {}
    params = params.copy()

    if kljuc.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {kljuc}"
    else:
        params["api_key"] = kljuc

    odgovor = requests.get(url, params=params, headers=headers, timeout=20)
    if odgovor.status_code == 401:
        raise RuntimeError("TMDb odbija kljuc. Provjeri da li je u tmdb_kljuc.txt API Key ili Read Access Token.")
    odgovor.raise_for_status()
    return odgovor


def pronadji_poster_na_tmdb(upit):
    cist_upit = ocisti_upit(upit)

    if not cist_upit:
        raise RuntimeError("Unesi naziv filma, npr. Interstellar.")

    odgovor = tmdb_get(
        TMDB_PRETRAGA_URL,
        params={
            "query": cist_upit,
            "include_adult": "false",
            "language": "en-US",
        },
    )

    rezultati = odgovor.json().get("results", [])
    if len(rezultati) == 0:
        raise RuntimeError("TMDb nije pronasao film za taj upit.")

    for film in rezultati:
        poster_path = film.get("poster_path")
        if poster_path:
            naslov = film.get("title", cist_upit)
            godina = film.get("release_date", "")[:4]
            return f"{TMDB_SLIKA_URL}{poster_path}", naslov, godina

    raise RuntimeError("Film je pronadjen, ali nema poster na TMDb.")


def skini_i_sacuvaj_sliku(url, ime_fajla):
    odgovor = requests.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        },
        timeout=20,
    )
    odgovor.raise_for_status()

    slika = Image.open(BytesIO(odgovor.content))
    slika = slika.convert("RGB")

    putanja = os.path.join(POSTERI_DIR, f"{ime_fajla}.jpg")
    slika.save(putanja, "JPEG", quality=90)
    return putanja


def osvjezi_ime_fajla(event=None):
    if korisnik_mijenja_ime.get():
        return

    predlog = napravi_ime_fajla(ocisti_upit(entry_upit.get()))
    entry_ime.delete(0, "end")
    entry_ime.insert(0, predlog)


def oznaci_rucnu_izmjenu(event=None):
    korisnik_mijenja_ime.set(True)


def pokreni_preuzimanje():
    upit = entry_upit.get().strip()
    ime_fajla = napravi_ime_fajla(entry_ime.get())

    if not upit:
        messagebox.showwarning("Paznja", "Unesi naziv filma, npr. Interstellar.")
        return

    if not ime_fajla:
        messagebox.showwarning("Paznja", "Unesi ime fajla.")
        return

    dugme_skini.configure(state="disabled", text="Preuzimam...")
    status_label.configure(text="Trazim film na TMDb...")
    root.update_idletasks()

    try:
        url, naslov, godina = pronadji_poster_na_tmdb(upit)
        dodatak = f" ({godina})" if godina else ""
        status_label.configure(text=f"Pronadjen film: {naslov}{dodatak}. Preuzimam poster...")
        root.update_idletasks()

        putanja = skini_i_sacuvaj_sliku(url, ime_fajla)
        relativna_putanja = os.path.relpath(putanja, APP_DIR)
        status_label.configure(text=f"Sacuvano: {relativna_putanja}")
        messagebox.showinfo(
            "Uspjesno",
            f"Pronadjen film: {naslov}{dodatak}\n\n"
            f"Poster je sacuvan kao:\n{relativna_putanja}\n\n"
            f"U filmovi.csv kolona poster treba da bude:\n{relativna_putanja.replace(os.sep, '/')}",
        )
    except Exception as greska:
        status_label.configure(text="Preuzimanje nije uspjelo.")
        messagebox.showerror("Greska", str(greska))
    finally:
        dugme_skini.configure(state="normal", text="Skini poster")


root = ctk.CTk()
root.title("Skidac postera")
root.geometry("520x330")
root.resizable(False, False)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

korisnik_mijenja_ime = tk.BooleanVar(value=False)

root.grid_columnconfigure(0, weight=1)

header = ctk.CTkFrame(root, fg_color="#111827", corner_radius=0)
header.grid(row=0, column=0, sticky="ew")
header.grid_columnconfigure(0, weight=1)

ctk.CTkLabel(
    header,
    text="TMDb skidac postera",
    font=("Georgia", 22, "bold"),
    text_color="#22c55e",
).grid(row=0, column=0, padx=18, pady=(18, 4), sticky="w")

ctk.CTkLabel(
    header,
    text="Upisi naziv filma, a alat ce sacuvati njegov poster u folder posteri.",
    text_color="#a8b3bd",
).grid(row=1, column=0, padx=18, pady=(0, 16), sticky="w")

forma = ctk.CTkFrame(root, fg_color="#15191f", corner_radius=8)
forma.grid(row=1, column=0, padx=18, pady=18, sticky="ew")
forma.grid_columnconfigure(1, weight=1)

ctk.CTkLabel(forma, text="Naziv filma:").grid(row=0, column=0, padx=(14, 8), pady=(16, 8), sticky="w")
entry_upit = ctk.CTkEntry(forma, placeholder_text="Interstellar")
entry_upit.grid(row=0, column=1, padx=(0, 14), pady=(16, 8), sticky="ew")
entry_upit.bind("<KeyRelease>", osvjezi_ime_fajla)

ctk.CTkLabel(forma, text="Ime fajla:").grid(row=1, column=0, padx=(14, 8), pady=8, sticky="w")
entry_ime = ctk.CTkEntry(forma, placeholder_text="interstellar")
entry_ime.grid(row=1, column=1, padx=(0, 14), pady=8, sticky="ew")
entry_ime.bind("<KeyRelease>", oznaci_rucnu_izmjenu)

dugme_skini = ctk.CTkButton(
    root,
    text="Skini poster",
    command=pokreni_preuzimanje,
    height=38,
    fg_color="#22c55e",
    hover_color="#16a34a",
)
dugme_skini.grid(row=2, column=0, padx=18, pady=(0, 12), sticky="ew")

status_label = ctk.CTkLabel(
    root,
    text="Koristi TMDb API kljuc iz tmdb_kljuc.txt.",
    text_color="#a8b3bd",
    wraplength=470,
)
status_label.grid(row=3, column=0, padx=18, pady=(0, 16), sticky="w")

root.mainloop()
