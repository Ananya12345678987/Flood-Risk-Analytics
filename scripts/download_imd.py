import imdlib as imd, time
failed = []
for y in range(2000, 2024):
    t = time.time()
    try:
        imd.get_data("rain", y, y, fn_format="yearwise", file_dir="data/raw/imd")
        print(f"{y} OK ({time.time()-t:.0f}s)", flush=True)
    except Exception as e:
        failed.append(y)
        print(f"{y} FAILED: {type(e).__name__}: {str(e)[:120]}", flush=True)
print("Failed years:", failed or "none")
