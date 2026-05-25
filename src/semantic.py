import torch
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import numpy as np
import cv2

class SemanticAnalyzer:
    def __init__(self, device="cuda" if torch.cuda.is_available() else "cpu"):
        self.device = device
        print(f"Loading CLIP model on {self.device}...")
        self.model_id = "openai/clip-vit-base-patch32"
        self.model = CLIPModel.from_pretrained(self.model_id).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(self.model_id)
        
        # Etiquetas para clasificación zero-shot
        # Más específicas para detectar mejor momentos personales/familiares
        self.labels = [
            "a photo of a family gathering or celebration",   # familia
            "a photo of a beautiful landscape or nature",     # paisaje
            "a screenshot of a phone or computer screen",     # screenshot
            "a group of people together smiling",             # grupo
            "a random object or document",                    # objeto random
            "a photo of a pet or animal",                     # mascotas
            "a photo of food or meal",                        # comida
            "a document, text, or paper",                     # documento
            "a selfie or close-up portrait",                  # selfie
            "a photo with a person in it",                    # persona
        ]
        
        # Configurar MediaPipe para detección de rostros
        self.face_detector = None
        try:
            import mediapipe.python.solutions.face_detection as mp_face_detection
            self.mp_face_detection = mp_face_detection
            self.face_detector = self.mp_face_detection.FaceDetection(
                model_selection=1, # 0 for short-range, 1 for full-range
                min_detection_confidence=0.5
            )
        except Exception as e:
            print(f"Advertencia: No se pudo cargar MediaPipe para detección de rostros. Se omitirá. ({e})")

    def analyze(self, image: Image.Image) -> dict:
        """
        Calcula el embedding visual y clasifica la imagen.
        """
        # 1. CLIP Analysis
        inputs = self.processor(
            text=self.labels, 
            images=image, 
            return_tensors="pt", 
            padding=True
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            # Normalizar para obtener embedding de similitud
            image_embeds = outputs.image_embeds
            image_embeds = image_embeds / image_embeds.norm(dim=-1, keepdim=True)
            
            # Obtener probabilidades zero-shot
            logits_per_image = outputs.logits_per_image
            probs = logits_per_image.softmax(dim=1).cpu().numpy()[0]
        
        scores = {label: float(prob) for label, prob in zip(self.labels, probs)}
        
        # 2. Face Detection con MediaPipe
        num_faces = 0
        if self.face_detector:
            open_cv_image = np.array(image)
            if len(open_cv_image.shape) == 3 and open_cv_image.shape[2] == 3:
                # MediaPipe espera RGB, así que no necesitamos cambiar de PIL a BGR, 
                # solo pasamos el array RGB
                pass
            else:
                # Si es RGBA o L, la convertimos
                open_cv_image = cv2.cvtColor(np.array(image.convert('RGB')), cv2.COLOR_BGR2RGB)
                
            try:
                results = self.face_detector.process(open_cv_image)
                if results.detections:
                    num_faces = len(results.detections)
            except Exception:
                pass
            
        # Mapeo de labels a claves semánticas
        family_label    = "a photo of a family gathering or celebration"
        group_label     = "a group of people together smiling"
        landscape_label = "a photo of a beautiful landscape or nature"
        screenshot_label = "a screenshot of a phone or computer screen"
        pet_label       = "a photo of a pet or animal"
        food_label      = "a photo of food or meal"
        document_label  = "a document, text, or paper"
        selfie_label    = "a selfie or close-up portrait"
        person_label    = "a photo with a person in it"

        return {
            "embedding": image_embeds.cpu().numpy()[0],
            "clip_scores": scores,
            "num_faces": num_faces,
            "is_family_moment": scores.get(family_label, 0) + scores.get(group_label, 0),
            "is_screenshot":    scores.get(screenshot_label, 0),
            "is_landscape":     scores.get(landscape_label, 0),
            "is_pet":           scores.get(pet_label, 0),
            "is_food":          scores.get(food_label, 0),
            "is_document":      scores.get(document_label, 0),
            "is_selfie":        scores.get(selfie_label, 0),
            "has_a_person":     scores.get(person_label, 0),
        }
