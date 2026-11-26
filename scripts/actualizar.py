#!/usr/bin/env python3
"""
Junta los datos oficiales del «Mapa apocalíptico de la Ciudad de México» y escribe data/alertas.json.

Fuentes:
  - Sismos: Servicio Sismológico Nacional (SSN, UNAM), RSS de últimos sismos.
    Complemento de 7 días (magnitud 4.5 o más): Servicio Geológico de EE. UU. (USGS).
  - Popocatépetl: reporte diario del Cenapred publicado en gob.mx/cenapred.
  - Calidad del aire: Índice AIRE Y SALUD de la Sedema (aire.cdmx.gob.mx).
  - Ciclones: Centro Nacional de Huracanes de EE. UU. (NHC), centro meteorológico regional de la OMM.
  - Alertas de la SGIRPC: data/sgirpc.json (se copian de sus publicaciones en X).

Si una fuente falla, se conserva el último dato bueno que ya estaba en data/alertas.json
y se marca con "ok": false. Solo usa la biblioteca estándar. Uso: python3 scripts/actualizar.py
"""
import html, json, os, re, time, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(RAIZ, "data", "alertas.json")
SGIRPC = os.path.join(RAIZ, "data", "sgirpc.json")
MX = timezone(timedelta(hours=-6))  # Hora del centro de México (sin horario de verano desde 2022)
UA = "Mozilla/5.0 (compatible; mapa-apocaliptico; +https://cdmx.eduardoluis.blog)"


def ahora():
    return datetime.now(MX).isoformat(timespec="seconds")


def bajar(url, timeout=40):
    last = None
    for intento in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-MX,es;q=0.9"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                b = r.read()
            for enc in ("utf-8", "latin-1"):
                try:
                    return b.decode(enc)
                except UnicodeDecodeError:
                    pass
        except Exception as e:  # reintenta ante fallas pasajeras
            last = e
            time.sleep(4 * (intento + 1))
    raise RuntimeError(f"{url}: {last}")


def texto(h):
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()


# ---------------- Sismos (SSN) ----------------
def sismos_ssn():
    xml = bajar("http://www.ssn.unam.mx/rss/ultimos-sismos.xml")
    raiz = ET.fromstring(xml)
    geo = "{http://www.w3.org/2003/01/geo/wgs84_pos#}"
    lista = []
    for it in raiz.iter("item"):
        tit = (it.findtext("title") or "").strip()
        desc = texto(it.findtext("description") or "")
        m = re.match(r"([\d.]+),\s*(.+)", tit)
        f = re.search(r"Fecha:\s*(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", desc)
        p = re.search(r"Profundidad:\s*([\d.]+)", desc)
        lat, lon = it.findtext(geo + "lat"), it.findtext(geo + "long")
        if not (m and f and lat and lon):
            continue
        t = datetime.strptime(f.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=MX)
        lista.append({"m": float(m.group(1)), "lugar": re.sub(r"\s+", " ", m.group(2)).strip(),
                      "t": t.isoformat(), "lat": float(lat), "lon": float(lon),
                      "prof": float(p.group(1)) if p else None, "fuente": "SSN"})
    if not lista:
        raise RuntimeError("RSS del SSN sin sismos")
    return lista


def sismos_usgs():
    j = json.loads(bajar("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"))
    lista = []
    for f in j["features"]:
        lon, lat, prof = f["geometry"]["coordinates"]
        if not (12 <= lat <= 33.5 and -118.5 <= lon <= -86):  # México y sus mares
            continue
        p = f["properties"]
        t = datetime.fromtimestamp(p["time"] // 1000, MX)
        lista.append({"m": round(p["mag"], 1), "lugar": p.get("place") or "", "t": t.isoformat(),
                      "lat": lat, "lon": lon, "prof": prof, "fuente": "USGS", "url": p.get("url")})
    return lista


# ---------------- Popocatépetl (Cenapred en gob.mx) ----------------
def popo():
    portada = bajar("https://www.gob.mx/cenapred")
    enlaces = re.findall(r'href="(/cenapred/articulos/monitoreo-del-volcan-popocatepetl[^"?#]*)', portada)
    if not enlaces:
        raise RuntimeError("no encontré el reporte del Popocatépetl en gob.mx/cenapred")
    url = "https://www.gob.mx" + enlaces[0]
    t = texto(bajar(url))
    s = re.search(r"Sem[aá]foro de Alerta Volc[aá]nica del Popocat[eé]petl se encuentra en\s+(verde|amarillo|rojo)\s+fase\s+(\d)", t, re.I)
    if not s:
        raise RuntimeError("no encontré el semáforo en el reporte")
    num = lambda pat: (lambda m: int(m.group(1)) if m else None)(re.search(pat, t, re.I))
    rumbo = re.search(r"con direcci[oó]n (?:al |hacia el |hacia )?((?:nor|sur)?(?:este|oeste|norte|sur)(?:[-\s](?:nor|sur)?(?:este|oeste|norte|sur))?)", t, re.I)
    fecha = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", t)
    return {"semaforo": s.group(1).lower(), "fase": int(s.group(2)),
            "exhalaciones": num(r"(\d+)\s+exhalaciones"), "tremor_min": num(r"(\d+)\s+minutos de tremor"),
            "explosiones": num(r"(\d+)\s+explosi[oó]n"), "rumbo": rumbo.group(1).lower() if rumbo else None,
            "fecha_texto": fecha.group(0) if fecha else None, "url": url}


# ---------------- Calidad del aire (Sedema) ----------------
def aire():
    t = texto(bajar("http://www.aire.cdmx.gob.mx/default.php"))
    i = re.search(r"[IÍ]ndice AIRE Y SALUD:\s*(BUENA|ACEPTABLE|MALA|MUY MALA|EXTREMADAMENTE MALA)", t, re.I)
    if not i:
        raise RuntimeError("no encontré el Índice AIRE Y SALUD")
    r = re.search(r"Nivel de riesgo:\s*([A-ZÁÉÍÓÚ ]+?)\s+(?:Contaminante|Recomendaci)", t, re.I)
    c = re.search(r"Contaminante\(s\):\s*([A-Z0-9.,\s]+?)\s+(?:Recomendaci|Pr[oó]x)", t)
    h = re.search(r"(\d{1,2}) horas", t)
    cont = re.search(r"(contingencia ambiental[^.]{0,120})", t, re.I)
    return {"indice": i.group(1).upper(), "riesgo": r.group(1).strip().upper() if r else None,
            "contaminantes": [x.strip() for x in c.group(1).split(",") if x.strip()] if c else [],
            "hora": int(h.group(1)) if h else None, "contingencia": cont.group(1).strip() if cont else None,
            "url": "http://www.aire.cdmx.gob.mx/default.php"}


# ---------------- Ciclones (NHC) ----------------
def ciclones():
    j = json.loads(bajar("https://www.nhc.noaa.gov/CurrentStorms.json"))
    lista = []
    for s in j.get("activeStorms", []):
        lista.append({"nombre": s.get("name"), "tipo": s.get("classification"), "lat": s.get("latitudeNumeric"),
                      "lon": s.get("longitudeNumeric"), "viento_kt": s.get("intensity"),
                      "rumbo": s.get("movementDir"), "vel_mph": s.get("movementSpeed"), "id": s.get("id"),
                      "cuenca": "Pacífico" if (s.get("binNumber") or "").startswith("EP") else "Atlántico"})
    return lista


def main():
    try:
        with open(OUT, encoding="utf-8") as f:
            viejo = json.load(f)
    except Exception:
        viejo = {}
    nuevo = {"generado": ahora()}

    def paso(clave, fn):
        try:
            nuevo[clave] = {"ok": True, "actualizado": ahora(), **fn()}
        except Exception as e:
            print(f"[aviso] {clave}: {e}")
            prev = viejo.get(clave) or {}
            nuevo[clave] = {**prev, "ok": False, "error": str(e)[:200]}

    def _sismos():
        ssn = sismos_ssn()
        try:
            extra = sismos_usgs()
        except Exception as e:
            print(f"[aviso] USGS: {e}")
            extra = (viejo.get("sismos") or {}).get("semana", [])
        return {"lista": ssn, "semana": extra}

    paso("sismos", _sismos)
    paso("popo", popo)
    paso("aire", aire)
    paso("ciclones", lambda: {"lista": ciclones()})
    with open(SGIRPC, encoding="utf-8") as f:
        nuevo["sgirpc"] = json.load(f)
    nuevo["sgirpc"].pop("_nota", None)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(nuevo, f, ensure_ascii=False, indent=1)
    print("Listo:", {k: (v.get("ok") if isinstance(v, dict) else None) for k, v in nuevo.items()})


if __name__ == "__main__":
    main()
