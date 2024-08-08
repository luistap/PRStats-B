import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import transforms
from PIL import Image

# Define the CNN model for character recognition
class CharCNN(nn.Module):
    def __init__(self):
        super(CharCNN, self).__init__()
        self.conv1 = nn.Conv2d(1, 16, kernel_size=3, padding=1)  # Conv layer
        self.conv2 = nn.Conv2d(16, 32, kernel_size=3, padding=1) # Another Conv layer
        self.pool = nn.MaxPool2d(2, 2)                           # Pooling layer
        self.fc1 = nn.Linear(32 * 7 * 7, 128)                    # Fully connected layer
        self.fc2 = nn.Linear(128, 2)                             # Output layer for 2 classes ('6' and '9')

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = torch.flatten(x, 1)  # Flatten the tensor for the fully connected layer
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return x

# Initialize the model and load the trained weights
model = CharCNN()
model.load_state_dict(torch.load('char_cnn.pth'))
model.eval()  # Set the model to evaluation mode

# Function to predict the character in a cropped image
def predict_character(image_path):
    # Image preprocessing
    transform = transforms.Compose([
        transforms.Grayscale(),        # Convert the image to grayscale
        transforms.Resize((28, 28)),   # Resize the image to 28x28 (adjust based on your training data)
        transforms.ToTensor(),         # Convert the image to a PyTorch tensor
        transforms.Normalize((0.5,), (0.5,))  # Normalize the image
    ])

    # Load the image
    image = Image.open(image_path)
    image = transform(image).unsqueeze(0)  # Add batch dimension

    # Make prediction
    with torch.no_grad():
        outputs = model(image)
        _, predicted = torch.max(outputs, 1)
    
    # Map the model's output to the corresponding character
    labels = {0: '6', 1: '9'}
    return labels[predicted.item()]

# Example usage
result = predict_character('C:/Users/ltper/PCKSTATS/chars_cropped/row_3_char_2.jpg')
print(f'The predicted character is: {result}')
