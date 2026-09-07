import sys

def test_imports():
    packages = [
        ("cv2", "opencv-python"),
        ("deepface", "deepface"),
        ("web3", "web3"),
        ("requests", "requests"),
        ("dotenv", "python-dotenv"),
        ("numpy", "numpy")
    ]
    
    all_ok = True
    for module_name, pkg_name in packages:
        try:
            __import__(module_name)
            print(f"OK: {pkg_name}")
        except Exception as e:
            print(f"FAIL: {pkg_name} - {type(e).__name__}: {str(e)}")
            all_ok = False
            
    if not all_ok:
        sys.exit(1)

if __name__ == "__main__":
    test_imports()
