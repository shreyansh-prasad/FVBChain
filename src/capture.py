import cv2
import time
import os

def capture_frame() -> str:
    """
    Captures a frame from the webcam (index 0) when the user presses SPACE.
    Returns the path to the saved image.
    """
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("[STAGE] capture: Error opening webcam")
        return ""
        
    print("[STAGE] capture: Webcam opened. Press SPACE to capture, or ESC to cancel.")
    
    saved_path = ""
    while True:
        ret, frame = cap.read()
        if not ret:
            print("[STAGE] capture: Failed to grab frame")
            break
            
        cv2.imshow("Capture (Press SPACE to snap)", frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == 32:  # SPACE key
            timestamp = int(time.time())
            # Ensure captured directory exists
            os.makedirs("captured", exist_ok=True)
            saved_path = f"captured/face_{timestamp}.jpg"
            cv2.imwrite(saved_path, frame)
            print(f"[STAGE] capture: Frame saved to {saved_path}")
            break
        elif key == 27:  # ESC key
            print("[STAGE] capture: Cancelled by user")
            break
            
    cap.release()
    cv2.destroyAllWindows()
    return saved_path

if __name__ == "__main__":
    path = capture_frame()
    if path:
        print(f"Test complete. Image at: {path}")
