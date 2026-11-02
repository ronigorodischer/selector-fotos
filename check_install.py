"""Small offline diagnostic, including an actual YuNet inference."""
import hashlib
from pathlib import Path
import sys


def main():
    import cv2
    import exifread
    import numpy as np
    import PIL
    import rawpy
    import send2trash
    root=Path(__file__).resolve().parent
    model=root/'models'/'face_detection_yunet_2026may.onnx'
    expected='ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0'
    if hashlib.sha256(model.read_bytes()).hexdigest()!=expected:
        raise RuntimeError('El modelo YuNet está incompleto o cambió. Recupera models/ desde Git.')
    detector=cv2.FaceDetectorYN.create(str(model),'',(320,320),0.8,0.3,500)
    detector.detect(np.zeros((320,320,3),dtype=np.uint8))
    from app import initial_source
    print(f'Python {sys.version.split()[0]} · OpenCV {cv2.__version__} · NumPy {np.__version__} · Pillow {PIL.__version__}')
    print('JPG, RAW, modelo de rostros y servidor local: disponibles.')


if __name__=='__main__':main()
