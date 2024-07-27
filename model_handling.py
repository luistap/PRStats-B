import os
import torch
import torchvision.transforms as transforms
from PIL import Image, ImageEnhance, ImageStat
from model import SimpleCNN  # Ensure this import matches the file name and class name
import torch.nn as nn

def load_model(model_path):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = SimpleCNN().to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()
    return model, device

def get_brightness(image):
    # Get brightness of the image
    stat = ImageStat.Stat(image.convert('L'))
    return stat.mean[0]

def adjust_brightness(image, target_brightness=128):
    current_brightness = get_brightness(image)
    # Adjust this threshold as needed for greater flexibility
    if current_brightness > 195:
        enhancer = ImageEnhance.Brightness(image)
        factor = target_brightness / current_brightness
        image = enhancer.enhance(factor)
        print(f"Brightness adjusted from {current_brightness:.2f} to {target_brightness:.2f}")
    else:
        print(f"Brightness adjustment not needed. Current brightness: {current_brightness:.2f}")
    return image

def preprocess_image(image_path, target_brightness=100):
    transform = transforms.Compose([
        transforms.Grayscale(),  # Convert image to grayscale
        transforms.Resize((28, 28)),  # Resize to 28x28 pixels
        transforms.ToTensor(),  # Convert to tensor
        transforms.Normalize((0.5,), (0.5,))  # Normalize the tensor
    ])

    image = Image.open(image_path)

    # Adjust brightness if necessary
    image = adjust_brightness(image, target_brightness)

    image = transform(image)
    image = image.unsqueeze(0)  # Add batch dimension
    return image

def predict(model, device, image):
    image = image.to(device)
    with torch.no_grad():
        output = model(image)
        _, predicted = torch.max(output, 1)
        predicted_class = predicted.item()
        return predicted_class

def main():
    # Hardcoded paths
    model_path = 'C:/Users/ltper/OneDrive/Desktop/cnn/models'
    image_path = r"C:\Users\ltper\PCKSTATS\chars_cropped\row_3_char_2.png".replace('\\', '/')
    
    # Load the model
    model, device = load_model(model_path)
    
    # Preprocess the image
    image = preprocess_image(image_path)
    
    # Get the prediction
    predicted_class = predict(model, device, image)
    
    # Interpret the prediction
    if predicted_class == 0:
        print("The predicted number is 6.")
    elif predicted_class == 1:
        print("The predicted number is 9.")
    else:
        print("Unknown prediction.")

if __name__ == "__main__":
    main()
