import csv
import os
import re
import subprocess
import sys
from datetime import date
from io import BytesIO
from tkinter import messagebox

import customtkinter as ctk

try:
    import requests
except ImportError:
    requests = None

try:
    from PIL import Image
except ImportError:
    Image = None


APP_DIR = os.path.dirname(os.path.abspath(__file__))
FILMOVI_CSV = os.path.join(APP_DIR, "filmovi.csv")
GLEDANI_CSV = os.path.join(APP_DIR, "gledani_filmovi.csv")
POSTERI_DIR = os.path.join(APP_DIR, "posteri")
TMDB_KLJUC_FAJL = os.path.join(APP_DIR, "tmdb_kljuc.txt")
TMDB_PRETRAGA_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SLIKA_URL = "https://image.tmdb.org/t/p/w500"

KOLONE_FILMOVI = ["id", "naziv", "godina", "zanr", "reziser", "trajanje", "opis", "poster"]
KOLONE_GLEDANI = ["id", "film_id", "datum_gledanja", "ocjena", "recenzija"]
SORTIRANJE_SVI = ["Naziv A-Z", "Naziv Z-A", "Najnoviji", "Najstariji"]
SORTIRANJE_GLEDANI = SORTIRANJE_SVI + ["Ocjena najveca", "Ocjena najmanja"]

filmovi = []
gledani = []
odabrani_film_id = None
odabrani_gledani_id = None
trenutni_prikaz = "svi"
trenutno_sortiranje = "Naziv A-Z"


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

os.makedirs(POSTERI_DIR, exist_ok=True)


def ucitaj_csv(putanja, kolone):
    if not os.path.exists(putanja):
        with open(putanja, "w", newline="", encoding="utf-8") as fajl:
            pisac = csv.DictWriter(fajl, fieldnames=kolone)
            pisac.writeheader()
        return []

    with open(putanja, newline="", encoding="utf-8") as fajl:
        return list(csv.DictReader(fajl))


def sacuvaj_gledane():
    with open(GLEDANI_CSV, "w", newline="", encoding="utf-8") as fajl:
        pisac = csv.DictWriter(fajl, fieldnames=KOLONE_GLEDANI)
        pisac.writeheader()
        pisac.writerows(gledani)


def sacuvaj_filmove():
    with open(FILMOVI_CSV, "w", newline="", encoding="utf-8") as fajl:
        pisac = csv.DictWriter(fajl, fieldnames=KOLONE_FILMOVI)
        pisac.writeheader()
        pisac.writerows(filmovi)


def sledeci_id(lista):
    najveci = 0
    for zapis in lista:
        try:
            broj = int(zapis["id"])
            if broj > najveci:
                najveci = broj
        except ValueError:
            pass
    return str(najveci + 1)


def nadji_film(film_id):
    for film in filmovi:
        if film["id"] == film_id:
            return film
    return None


def nadji_gledani(gledani_id):
    for zapis in gledani:
        if zapis["id"] == gledani_id:
            return zapis
    return None


def ocjena_u_zvjezdice(ocjena):
    try:
        broj = int(ocjena)
    except ValueError:
        return "Bez ocjene"
    return "*" * broj


def ucitaj_poster(film, velicina=(108, 160)):
    if Image is None:
        return None

    poster = film.get("poster", "").strip()
    if not poster:
        return None

    putanja = os.path.join(APP_DIR, poster)
    if not os.path.exists(putanja):
        return None

    try:
        slika = Image.open(putanja)
        return ctk.CTkImage(light_image=slika, dark_image=slika, size=velicina)
    except OSError:
        return None


def validiraj_ocjenu(ocjena):
    if not ocjena.isdigit():
        messagebox.showwarning("Paznja", "Ocjena mora biti broj od 1 do 5.")
        return False

    broj = int(ocjena)
    if broj < 1 or broj > 5:
        messagebox.showwarning("Paznja", "Ocjena mora biti izmedju 1 i 5.")
        return False

    return True


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
    if requests is None:
        raise RuntimeError("Biblioteka requests nije instalirana. Pokreni: pip install requests")

    cist_upit = ocisti_upit(upit)

    if not cist_upit:
        raise RuntimeError("Unesi naziv filma.")

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


def pronadji_poster_po_nazivu_i_godini(naziv, godina):
    upit_sa_godinom = f"{naziv} {godina}".strip()

    try:
        return pronadji_poster_na_tmdb(upit_sa_godinom)
    except Exception:
        if godina:
            return pronadji_poster_na_tmdb(naziv)
        raise


def skini_i_sacuvaj_poster(url, ime_fajla):
    if requests is None:
        raise RuntimeError("Biblioteka requests nije instalirana. Pokreni: pip install requests")

    if Image is None:
        raise RuntimeError("Biblioteka pillow nije instalirana. Pokreni: pip install pillow")

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


def otvori_skidac_postera():
    skripta = os.path.join(APP_DIR, "skidac_postera.py")
    if not os.path.exists(skripta):
        messagebox.showerror("Greska", "Nije pronadjen fajl skidac_postera.py.")
        return

    try:
        subprocess.Popen([sys.executable, skripta], cwd=APP_DIR)
    except Exception as greska:
        messagebox.showerror("Greska", f"Ne mogu otvoriti skidac postera:\n{greska}")


def reset_forme():
    global odabrani_gledani_id

    odabrani_gledani_id = None
    entry_datum.delete(0, "end")
    entry_datum.insert(0, date.today().isoformat())
    entry_ocjena.delete(0, "end")
    textbox_recenzija.delete("1.0", "end")
    status_label.configure(text="Odaberi film iz kataloga ili zapis iz dnevnika.")
    osvjezi_prikaz()


def odaberi_film(film_id):
    global odabrani_film_id, odabrani_gledani_id

    film = nadji_film(film_id)
    if film is None:
        return

    odabrani_film_id = film_id
    odabrani_gledani_id = None
    naslov_label.configure(text=f"{film['naziv']} ({film['godina']})")
    meta_label.configure(text=f"{film['zanr']} | {film['reziser']} | {film['trajanje']} min")
    opis_label.configure(text=film["opis"])
    status_label.configure(text="Film je odabran. Upisi ocjenu i recenziju.")
    reset_forme()
    odabrani_film_id = film_id
    osvjezi_prikaz()


def odaberi_gledani(gledani_id):
    global odabrani_film_id, odabrani_gledani_id

    zapis = nadji_gledani(gledani_id)
    if zapis is None:
        return

    film = nadji_film(zapis["film_id"])
    if film is None:
        return

    odabrani_film_id = film["id"]
    odabrani_gledani_id = gledani_id

    naslov_label.configure(text=f"{film['naziv']} ({film['godina']})")
    meta_label.configure(text=f"{film['zanr']} | {film['reziser']} | {film['trajanje']} min")
    opis_label.configure(text=film["opis"])

    entry_datum.delete(0, "end")
    entry_datum.insert(0, zapis["datum_gledanja"])
    entry_ocjena.delete(0, "end")
    entry_ocjena.insert(0, zapis["ocjena"])
    textbox_recenzija.delete("1.0", "end")
    textbox_recenzija.insert("1.0", zapis["recenzija"])
    status_label.configure(text="Odabran je zapis iz dnevnika gledanja.")
    osvjezi_prikaz()


def dodaj_u_gledane():
    if odabrani_film_id is None:
        messagebox.showwarning("Paznja", "Prvo odaberi film iz kataloga.")
        return

    datum = entry_datum.get().strip()
    ocjena = entry_ocjena.get().strip()
    recenzija = textbox_recenzija.get("1.0", "end").strip()

    if not datum or not ocjena:
        messagebox.showwarning("Paznja", "Datum i ocjena su obavezni.")
        return

    if not validiraj_ocjenu(ocjena):
        return

    zapis = {
        "id": sledeci_id(gledani),
        "film_id": odabrani_film_id,
        "datum_gledanja": datum,
        "ocjena": ocjena,
        "recenzija": recenzija,
    }
    gledani.append(zapis)
    sacuvaj_gledane()
    status_label.configure(text="Film je dodat u dnevnik gledanja.")
    prikazi_gledane()


def azuriraj_gledani():
    if odabrani_gledani_id is None:
        messagebox.showwarning("Paznja", "Prvo odaberi zapis iz dnevnika gledanja.")
        return

    zapis = nadji_gledani(odabrani_gledani_id)
    if zapis is None:
        messagebox.showerror("Greska", "Zapis nije pronadjen.")
        return

    datum = entry_datum.get().strip()
    ocjena = entry_ocjena.get().strip()
    recenzija = textbox_recenzija.get("1.0", "end").strip()

    if not datum or not ocjena:
        messagebox.showwarning("Paznja", "Datum i ocjena su obavezni.")
        return

    if not validiraj_ocjenu(ocjena):
        return

    zapis["datum_gledanja"] = datum
    zapis["ocjena"] = ocjena
    zapis["recenzija"] = recenzija
    sacuvaj_gledane()
    status_label.configure(text="Zapis je azuriran.")
    osvjezi_prikaz()


def obrisi_gledani():
    global odabrani_gledani_id

    if odabrani_gledani_id is None:
        messagebox.showwarning("Paznja", "Prvo odaberi zapis iz dnevnika gledanja.")
        return

    zapis = nadji_gledani(odabrani_gledani_id)
    film = nadji_film(zapis["film_id"]) if zapis else None
    naziv = film["naziv"] if film else "odabrani film"

    if not messagebox.askyesno("Potvrda", f"Obrisati zapis za {naziv}?"):
        return

    gledani.remove(zapis)
    odabrani_gledani_id = None
    sacuvaj_gledane()
    reset_forme()
    status_label.configure(text="Zapis je obrisan iz dnevnika.")


def filmovi_za_prikaz():
    pojam = entry_pretraga.get().strip().lower()
    if trenutni_prikaz == "gledani":
        lista = []
        for zapis in gledani:
            film = nadji_film(zapis["film_id"])
            if film is not None:
                lista.append((film, zapis))
    else:
        lista = [(film, None) for film in filmovi]

    if not pojam:
        return sortiraj_filmove(lista)

    rezultat = []
    for film, zapis in lista:
        tekst = f"{film['naziv']} {film['godina']} {film['zanr']} {film['reziser']}".lower()
        if zapis is not None:
            tekst += f" {zapis['ocjena']} {zapis['recenzija']}".lower()
        if pojam in tekst:
            rezultat.append((film, zapis))
    return sortiraj_filmove(rezultat)


def godina_kao_broj(film):
    try:
        return int(film["godina"])
    except ValueError:
        return 0


def ocjena_kao_broj(zapis):
    if zapis is None:
        return 0
    try:
        return int(zapis["ocjena"])
    except ValueError:
        return 0


def sortiraj_filmove(lista):
    if trenutno_sortiranje == "Naziv A-Z":
        return sorted(lista, key=lambda stavka: stavka[0]["naziv"].lower())
    if trenutno_sortiranje == "Naziv Z-A":
        return sorted(lista, key=lambda stavka: stavka[0]["naziv"].lower(), reverse=True)
    if trenutno_sortiranje == "Najnoviji":
        return sorted(lista, key=lambda stavka: godina_kao_broj(stavka[0]), reverse=True)
    if trenutno_sortiranje == "Najstariji":
        return sorted(lista, key=lambda stavka: godina_kao_broj(stavka[0]))
    if trenutno_sortiranje == "Ocjena najveca":
        return sorted(lista, key=lambda stavka: ocjena_kao_broj(stavka[1]), reverse=True)
    if trenutno_sortiranje == "Ocjena najmanja":
        return sorted(lista, key=lambda stavka: ocjena_kao_broj(stavka[1]))
    return lista


def promijeni_sortiranje(izbor):
    global trenutno_sortiranje
    trenutno_sortiranje = izbor
    osvjezi_prikaz()


def povezi_klik(widget, film_id, gledani_id):
    if gledani_id is None:
        widget.bind("<Button-1>", lambda dogadjaj: odaberi_film(film_id))
    else:
        widget.bind("<Button-1>", lambda dogadjaj: odaberi_gledani(gledani_id))


def napravi_karticu(roditelj, red, kolona, film, zapis):
    odabran = film["id"] == odabrani_film_id
    boja = "#182f25" if odabran else "#15191f"

    kartica = ctk.CTkFrame(roditelj, fg_color=boja, corner_radius=8)
    kartica.grid(row=red, column=kolona, padx=8, pady=8, sticky="nsew")
    kartica.grid_columnconfigure(0, weight=1)
    povezi_klik(kartica, film["id"], zapis["id"] if zapis else None)

    slika = ucitaj_poster(film)
    if slika is not None:
        poster = ctk.CTkLabel(kartica, text="", image=slika)
        poster.image = slika
    else:
        poster = ctk.CTkLabel(
            kartica,
            text=f"{film['naziv']}\n{film['godina']}",
            width=108,
            height=160,
            fg_color="#27323f",
            corner_radius=6,
            font=("Arial", 13, "bold"),
            wraplength=92,
        )
    poster.grid(row=0, column=0, padx=10, pady=(10, 6))
    povezi_klik(poster, film["id"], zapis["id"] if zapis else None)

    naziv = ctk.CTkLabel(kartica, text=film["naziv"], font=("Arial", 13, "bold"), wraplength=125)
    naziv.grid(row=1, column=0, padx=8, pady=(0, 2))
    povezi_klik(naziv, film["id"], zapis["id"] if zapis else None)

    detalji = ctk.CTkLabel(kartica, text=f"{film['godina']} | {film['zanr']}", text_color="#a8b3bd", font=("Arial", 11))
    detalji.grid(row=2, column=0, padx=8, pady=(0, 4))
    povezi_klik(detalji, film["id"], zapis["id"] if zapis else None)

    if zapis is not None:
        ocjena = ctk.CTkLabel(kartica, text=ocjena_u_zvjezdice(zapis["ocjena"]), text_color="#22c55e")
        ocjena.grid(row=3, column=0, padx=8, pady=(0, 10))
        povezi_klik(ocjena, film["id"], zapis["id"])


def osvjezi_prikaz():
    for widget in katalog_frame.winfo_children():
        widget.destroy()

    lista = filmovi_za_prikaz()
    if len(lista) == 0:
        tekst = "Nema gledanih filmova." if trenutni_prikaz == "gledani" else "Nema filmova za prikaz."
        ctk.CTkLabel(katalog_frame, text=tekst, text_color="#a8b3bd").grid(row=0, column=0, padx=20, pady=40)
        return

    broj_kolona = 4
    for kolona in range(broj_kolona):
        katalog_frame.grid_columnconfigure(kolona, weight=1)

    for indeks, (film, zapis) in enumerate(lista):
        red = indeks // broj_kolona
        kolona = indeks % broj_kolona
        napravi_karticu(katalog_frame, red, kolona, film, zapis)


def prikazi_sve():
    global trenutni_prikaz, trenutno_sortiranje
    trenutni_prikaz = "svi"
    if trenutno_sortiranje not in SORTIRANJE_SVI:
        trenutno_sortiranje = "Naziv A-Z"
    sortiranje_menu.configure(values=SORTIRANJE_SVI)
    sortiranje_menu.set(trenutno_sortiranje)
    lista_naslov.configure(text="Katalog filmova")
    btn_svi.configure(fg_color="#22c55e")
    btn_gledani.configure(fg_color="#334155")
    osvjezi_prikaz()


def prikazi_gledane():
    global trenutni_prikaz
    trenutni_prikaz = "gledani"
    sortiranje_menu.configure(values=SORTIRANJE_GLEDANI)
    sortiranje_menu.set(trenutno_sortiranje)
    lista_naslov.configure(text="Moj dnevnik gledanja")
    btn_svi.configure(fg_color="#334155")
    btn_gledani.configure(fg_color="#22c55e")
    osvjezi_prikaz()


def otvori_dodavanje_filma():
    dijalog = ctk.CTkToplevel(root)
    dijalog.title("Dodaj novi film")
    dijalog.geometry("520x620")
    dijalog.resizable(False, False)
    dijalog.grab_set()
    dijalog.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(
        dijalog,
        text="Dodaj film u katalog",
        font=("Georgia", 22, "bold"),
        text_color="#22c55e",
    ).grid(row=0, column=0, padx=18, pady=(18, 4), sticky="w")

    ctk.CTkLabel(
        dijalog,
        text="Ovaj film ide u filmovi.csv, ne u dnevnik gledanja.",
        text_color="#a8b3bd",
    ).grid(row=1, column=0, padx=18, pady=(0, 14), sticky="w")

    forma_film = ctk.CTkFrame(dijalog, fg_color="#15191f", corner_radius=8)
    forma_film.grid(row=2, column=0, padx=18, pady=8, sticky="ew")
    forma_film.grid_columnconfigure(1, weight=1)

    def dodaj_polje(red, tekst, placeholder=""):
        ctk.CTkLabel(forma_film, text=tekst).grid(row=red, column=0, padx=(14, 8), pady=7, sticky="w")
        entry = ctk.CTkEntry(forma_film, placeholder_text=placeholder)
        entry.grid(row=red, column=1, padx=(0, 14), pady=7, sticky="ew")
        return entry

    entry_naziv_novi = dodaj_polje(0, "Naziv:", "Interstellar")
    entry_godina_novi = dodaj_polje(1, "Godina:", "2014")
    entry_zanr_novi = dodaj_polje(2, "Zanr:", "Sci-Fi")
    entry_reziser_novi = dodaj_polje(3, "Reziser:", "Christopher Nolan")
    entry_trajanje_novi = dodaj_polje(4, "Trajanje:", "169")
    entry_poster_novi = dodaj_polje(5, "Poster:", "posteri/interstellar.jpg")

    ctk.CTkLabel(forma_film, text="Opis:").grid(row=6, column=0, columnspan=2, padx=14, pady=(10, 4), sticky="w")
    textbox_opis_novi = ctk.CTkTextbox(forma_film, height=105)
    textbox_opis_novi.grid(row=7, column=0, columnspan=2, padx=14, pady=(0, 14), sticky="ew")

    status_dijalog = ctk.CTkLabel(
        dijalog,
        text="Unesi podatke o filmu. Dugme Skini poster otvara poseban skidač, a ovdje upisi putanju npr. posteri/interstellar.jpg.",
        text_color="#a8b3bd",
        wraplength=470,
    )
    status_dijalog.grid(row=3, column=0, padx=18, pady=(6, 4), sticky="w")

    dugmad_dijalog = ctk.CTkFrame(dijalog, fg_color="transparent")
    dugmad_dijalog.grid(row=4, column=0, padx=18, pady=10, sticky="ew")
    dugmad_dijalog.grid_columnconfigure(0, weight=1)
    dugmad_dijalog.grid_columnconfigure(1, weight=1)

    def predlozi_poster_putanju(event=None):
        naziv = entry_naziv_novi.get().strip()
        if not naziv:
            return
        ime = napravi_ime_fajla(naziv)
        entry_poster_novi.delete(0, "end")
        entry_poster_novi.insert(0, f"posteri/{ime}.jpg")

    def sacuvaj_novi_film():
        naziv = entry_naziv_novi.get().strip()
        godina = entry_godina_novi.get().strip()
        zanr = entry_zanr_novi.get().strip()
        reziser = entry_reziser_novi.get().strip()
        trajanje = entry_trajanje_novi.get().strip()
        poster = entry_poster_novi.get().strip()
        opis = textbox_opis_novi.get("1.0", "end").strip()

        if not naziv or not godina or not zanr or not reziser or not trajanje:
            messagebox.showwarning("Paznja", "Naziv, godina, zanr, reziser i trajanje su obavezni.")
            return

        if not godina.isdigit() or not trajanje.isdigit():
            messagebox.showwarning("Paznja", "Godina i trajanje moraju biti brojevi.")
            return

        for film in filmovi:
            isti_naziv = film["naziv"].lower() == naziv.lower()
            ista_godina = film["godina"] == godina
            if isti_naziv and ista_godina:
                messagebox.showwarning("Paznja", "Taj film vec postoji u katalogu.")
                return

        novi_film = {
            "id": sledeci_id(filmovi),
            "naziv": naziv,
            "godina": godina,
            "zanr": zanr,
            "reziser": reziser,
            "trajanje": trajanje,
            "opis": opis,
            "poster": poster,
        }
        filmovi.append(novi_film)
        sacuvaj_filmove()
        prikazi_sve()
        odaberi_film(novi_film["id"])
        status_label.configure(text="Novi film je dodat u katalog.")
        dijalog.destroy()

    entry_naziv_novi.bind("<FocusOut>", predlozi_poster_putanju)

    btn_skini_novi = ctk.CTkButton(
        dugmad_dijalog,
        text="Skini poster",
        command=otvori_skidac_postera,
        fg_color="#22c55e",
        hover_color="#16a34a",
    )
    btn_skini_novi.grid(row=0, column=0, padx=(0, 6), pady=4, sticky="ew")

    ctk.CTkButton(
        dugmad_dijalog,
        text="Sacuvaj film",
        command=sacuvaj_novi_film,
        fg_color="#2563eb",
        hover_color="#1d4ed8",
    ).grid(row=0, column=1, padx=(6, 0), pady=4, sticky="ew")

    ctk.CTkButton(
        dijalog,
        text="Zatvori",
        command=dijalog.destroy,
        fg_color="#334155",
        hover_color="#475569",
    ).grid(row=5, column=0, padx=18, pady=(0, 16), sticky="ew")


root = ctk.CTk()
root.title("Mini Letterboxd Filmoteka")
root.geometry("1080x680")
root.minsize(960, 620)

root.grid_columnconfigure(0, weight=1)
root.grid_columnconfigure(1, weight=0)
root.grid_rowconfigure(2, weight=1)

header = ctk.CTkFrame(root, fg_color="#111827", corner_radius=0)
header.grid(row=0, column=0, columnspan=2, sticky="ew")
header.grid_columnconfigure(1, weight=1)

ctk.CTkLabel(header, text="Mini Letterboxd", font=("Georgia", 24, "bold"), text_color="#22c55e").grid(
    row=0, column=0, padx=18, pady=14, sticky="w"
)
ctk.CTkLabel(header, text="Katalog filmova i licni dnevnik gledanja", text_color="#a8b3bd").grid(
    row=0, column=1, padx=18, pady=14, sticky="e"
)

kontrole = ctk.CTkFrame(root, fg_color="#0f172a", corner_radius=0)
kontrole.grid(row=1, column=0, columnspan=2, sticky="ew")
kontrole.grid_columnconfigure(5, weight=1)

btn_svi = ctk.CTkButton(kontrole, text="Svi filmovi", command=prikazi_sve, fg_color="#22c55e", hover_color="#16a34a")
btn_svi.grid(row=0, column=0, padx=(16, 6), pady=10)

btn_gledani = ctk.CTkButton(kontrole, text="Gledani filmovi", command=prikazi_gledane, fg_color="#334155", hover_color="#475569")
btn_gledani.grid(row=0, column=1, padx=6, pady=10)

ctk.CTkButton(
    kontrole,
    text="Dodaj film",
    command=otvori_dodavanje_filma,
    fg_color="#2563eb",
    hover_color="#1d4ed8",
).grid(row=0, column=2, padx=6, pady=10)

ctk.CTkButton(
    kontrole,
    text="Skidac postera",
    command=otvori_skidac_postera,
    fg_color="#334155",
    hover_color="#475569",
).grid(row=0, column=3, padx=6, pady=10)

sortiranje_menu = ctk.CTkOptionMenu(
    kontrole,
    values=SORTIRANJE_SVI,
    command=promijeni_sortiranje,
    fg_color="#334155",
    button_color="#475569",
    button_hover_color="#64748b",
)
sortiranje_menu.grid(row=0, column=4, padx=6, pady=10)
sortiranje_menu.set(trenutno_sortiranje)

entry_pretraga = ctk.CTkEntry(kontrole, placeholder_text="Pretraga po nazivu, zanru, reziseru ili recenziji")
entry_pretraga.grid(row=0, column=5, padx=(12, 16), pady=10, sticky="ew")
entry_pretraga.bind("<KeyRelease>", lambda dogadjaj: osvjezi_prikaz())

lijevo = ctk.CTkFrame(root, fg_color="#0b1120", corner_radius=0)
lijevo.grid(row=2, column=0, sticky="nsew")
lijevo.grid_columnconfigure(0, weight=1)
lijevo.grid_rowconfigure(1, weight=1)

lista_naslov = ctk.CTkLabel(lijevo, text="Katalog filmova", font=("Arial", 17, "bold"), anchor="w")
lista_naslov.grid(row=0, column=0, padx=16, pady=(14, 4), sticky="ew")

katalog_frame = ctk.CTkScrollableFrame(lijevo, fg_color="#0b1120", corner_radius=0)
katalog_frame.grid(row=1, column=0, padx=8, pady=(0, 10), sticky="nsew")

desno = ctk.CTkFrame(root, fg_color="#111827", corner_radius=0, width=340)
desno.grid(row=2, column=1, sticky="ns")
desno.grid_propagate(False)
desno.grid_columnconfigure(0, weight=1)

ctk.CTkLabel(desno, text="Detalji filma", font=("Arial", 17, "bold")).grid(row=0, column=0, padx=18, pady=(18, 8), sticky="w")

naslov_label = ctk.CTkLabel(desno, text="Nijedan film nije odabran", font=("Arial", 18, "bold"), wraplength=290, justify="left")
naslov_label.grid(row=1, column=0, padx=18, pady=(4, 4), sticky="w")

meta_label = ctk.CTkLabel(desno, text="Odaberi film iz kataloga.", text_color="#a8b3bd", wraplength=290, justify="left")
meta_label.grid(row=2, column=0, padx=18, pady=(0, 8), sticky="w")

opis_label = ctk.CTkLabel(desno, text="", text_color="#cbd5e1", wraplength=290, justify="left")
opis_label.grid(row=3, column=0, padx=18, pady=(0, 16), sticky="w")

forma = ctk.CTkFrame(desno, fg_color="#15191f", corner_radius=8)
forma.grid(row=4, column=0, padx=18, pady=8, sticky="ew")
forma.grid_columnconfigure(1, weight=1)

ctk.CTkLabel(forma, text="Datum:").grid(row=0, column=0, padx=(12, 8), pady=(12, 6), sticky="w")
entry_datum = ctk.CTkEntry(forma)
entry_datum.grid(row=0, column=1, padx=(0, 12), pady=(12, 6), sticky="ew")
entry_datum.insert(0, date.today().isoformat())

ctk.CTkLabel(forma, text="Ocjena:").grid(row=1, column=0, padx=(12, 8), pady=6, sticky="w")
entry_ocjena = ctk.CTkEntry(forma, placeholder_text="1-5")
entry_ocjena.grid(row=1, column=1, padx=(0, 12), pady=6, sticky="ew")

ctk.CTkLabel(forma, text="Recenzija:").grid(row=2, column=0, columnspan=2, padx=12, pady=(8, 4), sticky="w")
textbox_recenzija = ctk.CTkTextbox(forma, height=100)
textbox_recenzija.grid(row=3, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="ew")

dugmad = ctk.CTkFrame(desno, fg_color="transparent")
dugmad.grid(row=5, column=0, padx=18, pady=8, sticky="ew")
dugmad.grid_columnconfigure(0, weight=1)
dugmad.grid_columnconfigure(1, weight=1)

ctk.CTkButton(dugmad, text="Dodaj gledanje", command=dodaj_u_gledane, fg_color="#22c55e", hover_color="#16a34a").grid(
    row=0, column=0, columnspan=2, padx=0, pady=(0, 8), sticky="ew"
)
ctk.CTkButton(dugmad, text="Azuriraj", command=azuriraj_gledani, fg_color="#ca8a04", hover_color="#a16207").grid(
    row=1, column=0, padx=(0, 5), pady=0, sticky="ew"
)
ctk.CTkButton(dugmad, text="Obrisi", command=obrisi_gledani, fg_color="#dc2626", hover_color="#b91c1c").grid(
    row=1, column=1, padx=(5, 0), pady=0, sticky="ew"
)
ctk.CTkButton(desno, text="Ocisti formu", command=reset_forme, fg_color="#334155", hover_color="#475569").grid(
    row=6, column=0, padx=18, pady=(4, 10), sticky="ew"
)

status_label = ctk.CTkLabel(desno, text="Odaberi film iz kataloga ili zapis iz dnevnika.", text_color="#a8b3bd", wraplength=290)
status_label.grid(row=7, column=0, padx=18, pady=(4, 10), sticky="w")

filmovi = ucitaj_csv(FILMOVI_CSV, KOLONE_FILMOVI)
gledani = ucitaj_csv(GLEDANI_CSV, KOLONE_GLEDANI)
osvjezi_prikaz()

root.mainloop()
