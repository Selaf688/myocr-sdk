"""Convert every PDF in a folder, up to 20 files per batch call.

    python batch_folder.py ./statements ./excel
"""
import pathlib
import sys

from myocr_client import MyOCRClient

src_dir = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "..")
out_dir = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "out")
out_dir.mkdir(exist_ok=True)

files = sorted(src_dir.glob("*.pdf"))
client = MyOCRClient()

for i in range(0, len(files), 20):
    batch = client.batch([str(f) for f in files[i:i + 20]], model="bank_statement")
    for err in batch.errors:
        print(f"Rejected {err['filename']}: {err['code']} {err['message']}")
    for job in batch.wait_all(timeout=1800):
        name = pathlib.Path(job.filename or job.request_id).stem
        if job.is_done:
            target = out_dir / f"{name}.xlsx"
            job.download(str(target))
            print(f"Saved {target}")
        else:
            print(f"{name}: job ended with status {job.status.value}")
