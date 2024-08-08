import cv2
import io
import os
import utilities
from model_handling import load_model, preprocess_image, predict

# Global model and device initialization
model, device = None, None

def initialize_model():
    global model, device
    model_path = 'models'
    model, device = load_model(model_path)
    model.eval()

def correct_mismatches(text):
    """Correct common OCR mismatches."""
    corrections = {
        'L': '1',
        'LL': '11',  # To handle double Ls seen as 11
        'o': '0',
        'о': '0',  # Cyrillic 'o'
        '°': '0',
        'י': '1',
        'сл': '5',
        'O1': '10',
        'No text found': '0',
        'N0 text f0und': '0',
        'N': '2'
    }
    for wrong, right in corrections.items():
        text = text.replace(wrong, right)
    return text


def process_stats(image_path):
    global model, device
    if model is None or device is None:
        initialize_model()  # Ensure the model is loaded if not already done

    img = cv2.imread(image_path)
    row_height = img.shape[0] // 5
    cropped_dir = 'chars_cropped'
    if not os.path.exists(cropped_dir):
        os.makedirs(cropped_dir)

    stats = []
    for i in range(5):
        row_img = img[i*row_height:(i+1)*row_height, :]
        char_width = row_img.shape[1] // 3

        row_stats = []
        for j in range(3):
            margin_w = int(0.1 * char_width)
            margin_h = int(0.1 * row_height)
            char_img = row_img[margin_h:-margin_h, (j*char_width+margin_w):((j+1)*char_width-margin_w)]
            char_path = os.path.join(cropped_dir, f'row_{i+1}_char_{j+1}.png')
            cv2.imwrite(char_path, char_img)

            _, buffer = cv2.imencode('.png', char_img)
            byte_img = io.BytesIO(buffer).getvalue()

            # Use utilities to perform OCR
            char_text = utilities.detect_text_byte(byte_img)

            # Correct any common OCR mismatches first
            char_text = correct_mismatches(char_text)

            # Additional ML check if OCR detects '6' or '9'
            if char_text in ['6', '9']:
                image_for_model = preprocess_image(char_path)  # Ensure this function returns correctly formatted tensor
                predicted_class = predict(model, device, image_for_model)
                char_text = '6' if predicted_class == 0 else '9'

            row_stats.append(char_text)

        stats.append(row_stats)
    return stats

if __name__ == "__main__":
    image_path = r"C:\Users\ltper\PCKSTATS\processed_image.png".replace('\\', '/')
    corrected_stats = process_stats(image_path)
    print(corrected_stats)
