#!/usr/bin/env python3
"""
source_file_copier.py
─────────────────────
Input1 klasöründeki (veya zip dosyasındaki) kaynak dosyaları, Input2 (hedef)
klasöründe ya da zip dosyasında recursive olarak arar ve eşleşme durumuna
göre kopyalar / uyarı verir.

Kullanım:
    python3 source_file_copier.py <input1> <input2> ["ignored1,ignored2"]

    input1 / input2 → klasör yolu VEYA .zip dosya yolu olabilir.

    Üçüncü parametre opsiyoneldir. Tırnak içinde, virgülle ayrılmış klasör
    adları verilir. Bu isimde klasörler hedef aramadan hariç tutulur.
    Örnek: "build,dist,.git,__pycache__"

Mantık:
    • Zip verilmişse, zip'in bulunduğu klasörde geçici bir alt klasöre
      otomatik olarak çıkartılır. İşlem bitince geçici klasör silinir.
    • Her kaynak dosya için hedef ağaçta aynı isimli dosyalar aranır.
    • 0 eşleşme  → hedef bulunamadı, atlanır (bilgi verilir).
    • 1 eşleşme  → kaynak dosya hedefin üzerine yazılır.
    • 2+ eşleşme → çakışma uyarısı verilir, işlem yapılmaz.
"""

import sys
import shutil
import zipfile
import tempfile
import atexit
from pathlib import Path
from datetime import datetime


# ── Renkli terminal çıktısı ────────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    GREEN  = "\033[92m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    GREY   = "\033[90m"
    WHITE  = "\033[97m"

def banner():
    print(f"""
{C.CYAN}{C.BOLD}╔══════════════════════════════════════════════╗
║        SOURCE FILE COPIER  v1.1              ║
╚══════════════════════════════════════════════╝{C.RESET}
""")

def fmt_path(p: Path) -> str:
    return f"{C.BLUE}{p}{C.RESET}"

def fmt_size(p: Path) -> str:
    try:
        s = p.stat().st_size
        for unit in ("B", "KB", "MB", "GB"):
            if s < 1024:
                return f"{s:.1f} {unit}"
            s /= 1024
        return f"{s:.1f} TB"
    except Exception:
        return "?"


# ── Zip yardımcıları ───────────────────────────────────────────────────────

# İşlem boyunca açık kalan geçici klasörleri takip et (atexit ile temizlenir)
_temp_dirs: list[Path] = []

def _cleanup_temps():
    for tmp in _temp_dirs:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
            print(f"\n{C.GREY}🗑  Geçici klasör silindi: {tmp}{C.RESET}")

atexit.register(_cleanup_temps)


def resolve_input(arg: str, label: str) -> tuple[Path, Path | None]:
    """
    Verilen argümanı klasör ya da zip dosyası olarak çözümler.

    Dönüş: (kullanılacak_klasör, zip_yolu_veya_None)
      - zip değilse zip_yolu None döner.
      - zip ise, zip'in yanındaki geçici klasöre çıkartılır ve o yol döner.
    """
    p = Path(arg).resolve()

    # ── Zip dosyası mı?
    if p.suffix.lower() == ".zip":
        if not p.exists():
            print(f"{C.RED}✖  {label} zip dosyası bulunamadı: {p}{C.RESET}")
            sys.exit(1)
        if not zipfile.is_zipfile(p):
            print(f"{C.RED}✖  {label} geçerli bir zip dosyası değil: {p}{C.RESET}")
            sys.exit(1)

        # Zip'in yanında geçici klasör aç
        tmp_parent = p.parent
        tmp_dir = Path(tempfile.mkdtemp(
            prefix=f"_sfc_tmp_{p.stem}_",
            dir=tmp_parent,
        ))
        _temp_dirs.append(tmp_dir)

        print(f"  {C.CYAN}📦 {label} zip dosyası çıkartılıyor...{C.RESET}")
        print(f"     {fmt_path(p)}  →  {fmt_path(tmp_dir)}")

        with zipfile.ZipFile(p, "r") as zf:
            zf.extractall(tmp_dir)

        file_count = sum(1 for f in tmp_dir.rglob("*") if f.is_file())
        print(f"     {C.GREEN}✔  {file_count} dosya çıkartıldı.{C.RESET}\n")

        return tmp_dir, p

    # ── Normal klasör
    if not p.exists():
        print(f"{C.RED}✖  {label} bulunamadı: {p}{C.RESET}")
        sys.exit(1)
    if not p.is_dir():
        print(f"{C.RED}✖  {label} ne bir klasör ne de bir zip dosyası: {p}{C.RESET}")
        sys.exit(1)

    return p, None


# ── Ana mantık ─────────────────────────────────────────────────────────────

def collect_sources(folder: Path) -> list[Path]:
    """Input1 içindeki tüm dosyaları (recursive) döndür."""
    return [p for p in folder.rglob("*") if p.is_file()]


def find_matches(filename: str, root: Path, ignored: set) -> list[Path]:
    """root içinde verilen isimde dosyaları recursive ara; ignored klasörleri atla."""
    results = []
    for p in root.rglob(filename):
        if not p.is_file():
            continue
        if ignored and ignored.intersection(set(p.parts)):
            continue
        results.append(p)
    return results


def run(src_arg: str, dst_arg: str, ignored: set):
    banner()

    # ── Girdileri çözümle (zip ise çıkart)
    src_root, src_zip = resolve_input(src_arg, "INPUT1 (kaynak)")
    dst_root, dst_zip = resolve_input(dst_arg, "INPUT2 (hedef)")

    # ── Başlık bilgisi
    src_label = f"{src_zip}  {C.GREY}(zip → {src_root}){C.RESET}" if src_zip else str(src_root)
    dst_label = f"{dst_zip}  {C.GREY}(zip → {dst_root}){C.RESET}" if dst_zip else str(dst_root)

    print(f"  {C.BOLD}Kaynak        :{C.RESET} {C.BLUE}{src_label}{C.RESET}")
    print(f"  {C.BOLD}Hedef         :{C.RESET} {C.BLUE}{dst_label}{C.RESET}")
    if ignored:
        print(f"  {C.BOLD}Atlanan klasör:{C.RESET} {C.YELLOW}{', '.join(sorted(ignored))}{C.RESET}")
    print(f"  {C.BOLD}Başlangıç     :{C.RESET} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    print(f"{C.GREY}{'─'*60}{C.RESET}\n")

    sources = collect_sources(src_root)

    if not sources:
        print(f"{C.YELLOW}⚠  Kaynak klasörde hiç dosya bulunamadı.{C.RESET}")
        sys.exit(0)

    print(f"{C.BOLD}Kaynak dosya sayısı: {len(sources)}{C.RESET}\n")

    # ── Sayaçlar
    stats = {
        "copied":    0,
        "conflict":  0,
        "not_found": 0,
    }
    log: list[dict] = []

    # ── Her kaynak dosya için işlem
    for src in sources:
        rel  = src.relative_to(src_root)
        name = src.name
        matches = find_matches(name, dst_root, ignored)

        print(f"{C.BOLD}► {rel}{C.RESET}  {C.GREY}({fmt_size(src)}){C.RESET}")

        if len(matches) == 0:
            print(f"  {C.YELLOW}⊘  No match found in target.{C.RESET}")
            print(f"     {C.BOLD}Enter destination path (or press Enter to skip):{C.RESET} ", end="", flush=True)
            try:
                user_input = input().strip()
            except (EOFError, KeyboardInterrupt):
                user_input = ""

            if not user_input:
                msg = "No match found — skipped by user."
                print(f"  {C.GREY}   Skipped.{C.RESET}")
                stats["not_found"] += 1
                log.append({"file": str(rel), "status": "NOT_FOUND", "detail": msg})
            else:
                manual_dst = Path(user_input).expanduser().resolve()
                if manual_dst.is_dir():
                    # User gave a folder → place file inside it
                    manual_dst = manual_dst / src.name
                if not manual_dst.parent.exists():
                    print(f"  {C.RED}✖  Directory does not exist: {manual_dst.parent} — skipped.{C.RESET}")
                    stats["not_found"] += 1
                    log.append({"file": str(rel), "status": "NOT_FOUND", "detail": f"Manual path invalid: {manual_dst}"})
                else:
                    old_size = fmt_size(manual_dst) if manual_dst.exists() else "—"
                    try:
                        shutil.copy2(src, manual_dst)
                        print(f"  {C.GREEN}✔  Copied  →  {fmt_path(manual_dst)}")
                        print(f"     Old size: {old_size}  |  New size: {fmt_size(manual_dst)}{C.RESET}")
                        stats["copied"] += 1
                        log.append({
                            "file":   str(rel),
                            "status": "COPIED",
                            "detail": f"→ {manual_dst} (manual)  [old: {old_size}, new: {fmt_size(manual_dst)}]",
                        })
                    except Exception as e:
                        print(f"  {C.RED}✖  Copy error: {e}{C.RESET}")
                        log.append({"file": str(rel), "status": "ERROR", "detail": str(e)})

        elif len(matches) == 1:
            dst = matches[0]
            old_size = fmt_size(dst)
            try:
                shutil.copy2(src, dst)
                print(f"  {C.GREEN}✔  Kopyalandı  →  {fmt_path(dst.relative_to(dst_root))}")
                print(f"     Eski boyut: {old_size}  |  Yeni boyut: {fmt_size(dst)}{C.RESET}")
                stats["copied"] += 1
                log.append({
                    "file":   str(rel),
                    "status": "COPIED",
                    "detail": f"→ {dst}  [eski: {old_size}, yeni: {fmt_size(dst)}]",
                })
            except Exception as e:
                print(f"  {C.RED}✖  Kopyalama hatası: {e}{C.RESET}")
                log.append({"file": str(rel), "status": "ERROR", "detail": str(e)})

        else:
            print(f"  {C.YELLOW}⚠  ÇAKIŞMA — {len(matches)} eşleşme bulundu, işlem yapılmadı:{C.RESET}")
            for m in matches:
                print(f"     {C.YELLOW}• {m}{C.RESET}")
            stats["conflict"] += 1
            log.append({
                "file":   str(rel),
                "status": "CONFLICT",
                "detail": f"{len(matches)} eşleşme: " + " | ".join(str(m) for m in matches),
            })

        print()

    # ── Özet rapor
    status_meta = {
        "COPIED":    (C.GREEN,  "✔", "KOPYALANDI "),
        "CONFLICT":  (C.YELLOW, "⚠", "ÇAKIŞMA    "),
        "NOT_FOUND": (C.GREY,   "⊘", "BULUNAMADI "),
        "ERROR":     (C.RED,    "✖", "HATA       "),
    }

    print(f"{C.GREY}{'─'*60}{C.RESET}")
    print(f"\n{C.BOLD}{C.WHITE}  ÖZET RAPOR  ({len(log)} dosya){C.RESET}\n")

    for entry in log:
        color, icon, label = status_meta.get(entry["status"], (C.WHITE, "?", entry["status"]))
        print(f"  {color}{icon} {label}  {C.BOLD}{entry['file']}{C.RESET}")
        print(f"           {C.GREY}{entry['detail']}{C.RESET}")

    print(f"\n{C.GREY}{'─'*60}{C.RESET}")
    print(f"  {C.GREEN}✔  Kopyalanan       : {stats['copied']}{C.RESET}")
    print(f"  {C.YELLOW}⚠  Çakışma (atlandı): {stats['conflict']}{C.RESET}")
    print(f"  {C.GREY}⊘  Hedefte yok      : {stats['not_found']}{C.RESET}")
    print(f"\n  {C.BOLD}Toplam işlenen     : {len(sources)}{C.RESET}")
    print(f"  {C.BOLD}Bitiş              : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{C.RESET}\n")

    # ── Detaylı log dosyası
    log_path = Path("copy_report.log")
    with log_path.open("w", encoding="utf-8") as f:
        f.write("SOURCE FILE COPIER — Rapor\n")
        f.write(f"Tarih   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Kaynak  : {src_zip or src_root}\n")
        f.write(f"Hedef   : {dst_zip or dst_root}\n")
        if ignored:
            f.write(f"Atlanan : {', '.join(sorted(ignored))}\n")
        f.write("─" * 60 + "\n\n")
        for entry in log:
            f.write(f"[{entry['status']:10s}]  {entry['file']}\n")
            f.write(f"             {entry['detail']}\n\n")
        f.write("─" * 60 + "\n")
        f.write(f"Kopyalanan: {stats['copied']}  |  "
                f"Çakışma: {stats['conflict']}  |  "
                f"Bulunamadı: {stats['not_found']}\n")

    print(f"  {C.CYAN}📄 Detaylı log kaydedildi: {log_path.resolve()}{C.RESET}\n")

    # atexit → geçici klasörler otomatik silinir


# ── Giriş noktası ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print(f"\n{C.YELLOW}Kullanım: python3 source_file_copier.py <input1> <input2> [\"ignored1,ignored2\"]")
        print(f"  input1 / input2 → klasör yolu veya .zip dosyası{C.RESET}\n")
        sys.exit(1)

    ignored: set = set()
    if len(sys.argv) == 4:
        ignored = {name.strip() for name in sys.argv[3].split(",") if name.strip()}

    run(sys.argv[1], sys.argv[2], ignored)