import cv2
import mediapipe as mp
import numpy as np
import time
from pygame import mixer
from collections import deque

# ————— Configurações ——————
# Thresholds configuráveis
DISTANCIA_MINIMA_REL = 0.15    # Proporção mínima (rosto-tronco / largura do tronco)
ANGULO_MAXIMO = 15             # Ângulo máximo de inclinação (graus)
ALERTA_INTERVALO = 5           # segundos entre alertas

# Janela para suavização
WINDOW_SIZE = 5

# Arquivo de som
ALERTA_SONORO = "alerta.wav"
# ——————————————————————————

def init_audio(path):
    mixer.init()
    mixer.music.load(path)

def calcular_medias(janela):
    return sum(janela) / len(janela) if janela else 0

def calcular_metricas(landmarks):
    # Extrai pontos
    O_L = np.array([landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].x,
                    landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].y])
    O_R = np.array([landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].x,
                    landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].y])
    E_L = np.array([landmarks[mp_pose.PoseLandmark.LEFT_EAR.value].x,
                    landmarks[mp_pose.PoseLandmark.LEFT_EAR.value].y])
    NOSE = np.array([landmarks[mp_pose.PoseLandmark.NOSE.value].x,
                     landmarks[mp_pose.PoseLandmark.NOSE.value].y])

    # Largura do tronco (ombro a ombro)
    largura_tronco = np.linalg.norm(O_R - O_L) + 1e-6

    # Distância vertical (orelha-tronco) normalizada
    dist_vertical_rel = abs(E_L[1] - O_L[1]) / largura_tronco

    # Ponto médio dos ombros
    mid_ombros = (O_L + O_R) / 2
    # Vetor do tronco
    vetor_tronco = NOSE - mid_ombros
    # Vetor vertical (para cima na imagem é [0, -1])
    vetor_vertical = np.array([0, -1])

    # Ângulo entre tronco e vertical
    cos_theta = np.dot(vetor_tronco, vetor_vertical) / (
        np.linalg.norm(vetor_tronco) * np.linalg.norm(vetor_vertical) + 1e-6
    )
    angulo_inclinacao = np.degrees(np.arccos(np.clip(cos_theta, -1.0, 1.0)))

    return dist_vertical_rel, angulo_inclinacao

if __name__ == "__main__":
    # Inicialização
    init_audio(ALERTA_SONORO)
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(min_detection_confidence=0.7, min_tracking_confidence=0.7)
    mp_drawing = mp.solutions.drawing_utils

    cap = cv2.VideoCapture(0)
    ultimo_alerta = time.time() - ALERTA_INTERVALO

    # Fila para suavização
    janela_dist = deque(maxlen=WINDOW_SIZE)
    janela_ang = deque(maxlen=WINDOW_SIZE)

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                continue

            img = cv2.flip(frame, 1)
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            results = pose.process(img_rgb)

            if results.pose_landmarks:
                dist_rel, ang_incli = calcular_metricas(results.pose_landmarks.landmark)

                # Suavização
                janela_dist.append(dist_rel)
                janela_ang.append(ang_incli)
                dist_suave = calcular_medias(janela_dist)
                ang_suave = calcular_medias(janela_ang)

                # Verifica postura inadequada
                if dist_suave < DISTANCIA_MINIMA_REL or ang_suave > ANGULO_MAXIMO:
                    cv2.putText(img, "POSTURA INADEQUADA!", (30, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

                    # Alerta sonoro periódco
                    if time.time() - ultimo_alerta >= ALERTA_INTERVALO:
                        mixer.music.play()
                        ultimo_alerta = time.time()

                # Desenha esqueleto
                mp_drawing.draw_landmarks(img, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)

            cv2.imshow("Alerta de Postura", img)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except Exception as e:
        print(f"[ERRO] {e}")

    finally:
        cap.release()
        cv2.destroyAllWindows()
