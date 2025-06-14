import os
import cv2
import mediapipe as mp
import numpy as np
import time
from pygame import mixer
from collections import deque

# ————— Configurações ——————
DISTANCIA_MINIMA_REL = 0.15    # Proporção mínima (orelha–ombro / largura do tronco)
ANGULO_MAXIMO       = 15       # Ângulo máximo de inclinação (graus)
ALERTA_INTERVALO    = 5        # segundos entre alertas
WINDOW_SIZE         = 5        # tamanho da janela para suavização
SHOULDER_VIS_THRESH = 0.5      # visibility mínima aceitável dos ombros
ALERTA_SONORO       = "alerta.mp3"
TOLERANCIA_DIST     = 0.08     # Tolerância para distância relativa
TOLERANCIA_ANG      = 5        # Tolerância para ângulo (graus)
# ——————————————————————————

def init_audio(filename):
    mixer.init()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, filename)
    if not os.path.exists(path):
        print(f"[AVISO] Arquivo de áudio não encontrado em: {path}")
        return False
    mixer.music.load(path)
    return True

def calcular_medias(janela):
    return sum(janela) / len(janela) if janela else 0

def calcular_metricas(landmarks):
    # Extrai pontos como arrays e visibility
    O_L = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
    O_R = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
    E_L = landmarks[mp_pose.PoseLandmark.LEFT_EAR.value]
    NOSE = landmarks[mp_pose.PoseLandmark.NOSE.value]

    pt_OL = np.array([O_L.x, O_L.y])
    pt_OR = np.array([O_R.x, O_R.y])
    pt_EL = np.array([E_L.x, E_L.y])
    pt_NO = np.array([NOSE.x, NOSE.y])

    # Largura do tronco
    largura_tronco = np.linalg.norm(pt_OR - pt_OL) + 1e-6
    dist_vertical_rel = abs(pt_EL[1] - pt_OL[1]) / largura_tronco

    # Ângulo entre tronco e vertical
    mid_ombros = (pt_OL + pt_OR) / 2
    vetor_tronco = pt_NO - mid_ombros
    vetor_vertical = np.array([0, -1])
    cos_theta = np.dot(vetor_tronco, vetor_vertical) / (
        np.linalg.norm(vetor_tronco) * np.linalg.norm(vetor_vertical) + 1e-6
    )
    angulo_inclinacao = np.degrees(np.arccos(np.clip(cos_theta, -1.0, 1.0)))

    # Devolve também as visibilities dos ombros
    return dist_vertical_rel, angulo_inclinacao, O_L.visibility, O_R.visibility

if __name__ == "__main__":
    has_audio = init_audio(ALERTA_SONORO)

    mp_pose  = mp.solutions.pose
    pose     = mp_pose.Pose(min_detection_confidence=0.7, min_tracking_confidence=0.7)
    mp_draw  = mp.solutions.drawing_utils

    cap      = cv2.VideoCapture(0)
    ultimo   = time.time() - ALERTA_INTERVALO
    janela_d = deque(maxlen=WINDOW_SIZE)
    janela_a = deque(maxlen=WINDOW_SIZE)
    
    # Variáveis para postura desejada
    dist_desejada = None
    ang_desejado = None
    salvando_postura = False
    tempo_salvamento = 0

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: continue

            img     = cv2.flip(frame, 1)
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            res     = pose.process(img_rgb)

            if res.pose_landmarks:
                dist_rel, ang_incli, vis_l, vis_r = calcular_metricas(res.pose_landmarks.landmark)

                # Checa se os ombros estão "visíveis" o suficiente
                falta_ombro = (vis_l < SHOULDER_VIS_THRESH) or (vis_r < SHOULDER_VIS_THRESH)

                # Suavização
                janela_d.append(dist_rel)
                janela_a.append(ang_incli)
                dist_s = calcular_medias(janela_d)
                ang_s  = calcular_medias(janela_a)

                # Verificação de postura inadequada
                condicao_alerta = False
                msg_alerta = ""
                
                # 1. Verificar visibilidade dos ombros
                if falta_ombro:
                    condicao_alerta = True
                    msg_alerta = "OMBROS NAO VISIVEIS"
                
                # 2. Verificar postura desejada (se definida)
                elif dist_desejada is not None and ang_desejado is not None:
                    dist_diferenca = abs(dist_s - dist_desejada)
                    ang_diferenca = abs(ang_s - ang_desejado)
                    
                    if dist_diferenca > TOLERANCIA_DIST or ang_diferenca > TOLERANCIA_ANG:
                        condicao_alerta = True
                        msg_alerta = "POSTURA DESVIADA"
                        
                        # Detalhes do desvio
                        desvio_dist = dist_s - dist_desejada
                        desvio_ang = ang_s - ang_desejado
                        
                        if desvio_dist < 0:
                            msg_alerta += " (CABECA BAIXA)"
                        else:
                            msg_alerta += " (CABECA ALTA)"
                            
                        if desvio_ang > 0:
                            msg_alerta += " (INCLINADO)"
                
                # 3. Fallback para limiares fixos (se não houver postura desejada)
                else:
                    if dist_s < DISTANCIA_MINIMA_REL or ang_s > ANGULO_MAXIMO:
                        condicao_alerta = True
                        msg_alerta = "POSTURA INADEQUADA"

                # Acionar alertas se necessário
                if condicao_alerta:
                    cv2.putText(img, msg_alerta, (30, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
                    if has_audio and time.time() - ultimo >= ALERTA_INTERVALO:
                        mixer.music.play()
                        ultimo = time.time()

                # Desenhar métricas na tela
                y_pos = 80
                cv2.putText(img, f"Dist: {dist_s:.3f} ({'DESEJADA' if dist_desejada is None else f'Alvo: {dist_desejada:.3f}'})", 
                            (30, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
                cv2.putText(img, f"Angulo: {ang_s:.1f} ({'DESEJADO' if ang_desejado is None else f'Alvo: {ang_desejado:.1f}'})", 
                            (30, y_pos+30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
                
                # Mostrar status de salvamento
                if salvando_postura:
                    if time.time() - tempo_salvamento < 2:  # Mostrar por 2 segundos
                        cv2.putText(img, "POSTURA DESEJADA SALVA!", (30, y_pos+80),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,255), 2)
                    else:
                        salvando_postura = False

                mp_draw.draw_landmarks(img, res.pose_landmarks, mp_pose.POSE_CONNECTIONS)

            # Instruções de uso
            cv2.putText(img, "'s': Salvar postura atual", (10, img.shape[0]-60), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 1)
            cv2.putText(img, "'r': Resetar postura desejada", (10, img.shape[0]-30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 1)
            
            cv2.imshow("Alerta de Postura", img)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                # Salvar postura atual como desejada
                dist_desejada = dist_s
                ang_desejado = ang_s
                salvando_postura = True
                tempo_salvamento = time.time()
                print(f"Postura desejada salva! Dist: {dist_desejada:.3f}, Ang: {ang_desejado:.1f}")
            elif key == ord('r'):
                # Resetar postura desejada
                dist_desejada = None
                ang_desejado = None
                print("Postura desejada resetada!")

    finally:
        cap.release()
        cv2.destroyAllWindows()