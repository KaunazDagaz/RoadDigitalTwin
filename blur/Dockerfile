FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -c "from ultralytics import YOLO; YOLO('models/yolov8n.pt')"
RUN python -c "from huggingface_hub import hf_hub_download; hf_hub_download('morsetechlab/yolov11-license-plate-detection', 'license-plate-finetune-v1n.pt', local_dir='models')"

ENTRYPOINT ["python", "blur.py"]
