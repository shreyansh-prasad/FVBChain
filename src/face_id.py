from deepface import DeepFace
import os
import tempfile


def get_embedding(image_path: str) -> dict:
    """
    Extracts a 512-d face embedding from the provided image using DeepFace and Facenet512.
    Returns a dictionary with 'embedding', 'facial_area', and 'model'.
    If no face is detected, returns an error dict.
    """
    print(f"[STAGE] face_id: Extracting embedding for {image_path}")
    try:
        # DeepFace.represent returns a list of representations (one for each detected face).
        # We take the first one [0].
        result = DeepFace.represent(
            img_path=image_path,
            model_name="Facenet512",
            detector_backend="mtcnn"
        )

        # In case it returned a list of dicts, grab the first face found
        if isinstance(result, list) and len(result) > 0:
            face_data = result[0]
        else:
            face_data = result

        embedding = face_data.get("embedding", [])
        facial_area = face_data.get("facial_area", {})

        print("[STAGE] face_id: Successfully extracted face embedding")
        return {
            "embedding": embedding,
            "facial_area": facial_area,
            "model": "Facenet512"
        }
    except ValueError as e:
        # DeepFace raises ValueError if no face is detected
        print(f"[STAGE] face_id: No face detected in {image_path}")
        return {"error": "no_face_detected"}
    except Exception as e:
        print(f"[STAGE] face_id: Unexpected error - {type(e).__name__}: {str(e)}")
        return {"error": str(e)}


def crop_face(image_path: str, facial_area: dict, padding: float = 0.40) -> str | None:
    """
    Crops a padded face region from image_path using the bounding box
    returned by DeepFace (facial_area keys: x, y, w, h).
    Saves it to a temp JPEG and returns the path.
    Returns None if anything fails (caller falls back to original image).

    padding=0.40 adds 40% of face width/height on each side so the crop
    includes the full head (forehead, chin, ears) — important for Yandex.
    """
    try:
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        iw, ih = img.size

        x = facial_area.get("x", 0)
        y = facial_area.get("y", 0)
        w = facial_area.get("w", iw)
        h = facial_area.get("h", ih)

        # Apply padding symmetrically
        pad_x = int(w * padding)
        pad_y = int(h * padding)

        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = min(iw, x + w + pad_x)
        y2 = min(ih, y + h + pad_y)

        cropped = img.crop((x1, y1, x2, y2))

        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix="_face_crop.jpg", dir=os.path.dirname(image_path) or "."
        )
        cropped.save(tmp.name, "JPEG", quality=95)
        print(f"[STAGE] face_id: Face crop saved -> {tmp.name} (box: {x1},{y1},{x2},{y2})")
        return tmp.name

    except Exception as e:
        print(f"[STAGE] face_id: crop_face failed ({type(e).__name__}: {e}) — will use original image.")
        return None



if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
    else:
        test_path = "captured/test.jpg"
        print("[STAGE] face_id: No path provided, using default (will likely fail if file doesn't exist).")
        
    print(f"[STAGE] face_id: Running standalone test on {test_path}")
    res = get_embedding(test_path)
    
    if "error" in res:
        print(f"[STAGE] face_id: Result -> {res}")
    else:
        emb = res.get("embedding", [])
        print(f"[STAGE] face_id: Result -> Embedding length: {len(emb)}")
        print(f"[STAGE] face_id: Result -> Facial area: {res.get('facial_area')}")
