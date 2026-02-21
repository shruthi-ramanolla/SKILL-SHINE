# analyzers.py
# Simple analysis heuristics for MVP.
# For dance/sports -> pose analysis via MediaPipe
# For singing -> audio pitch stability via librosa

import os
import numpy as np

def analyze_file(path, talent_type):
    t = talent_type.lower()
    try:
        if t in ("dance", "sports", "sport", "movement"):
            return analyze_video_pose(path)
        elif t in ("singing", "music", "vocal"):
            return analyze_audio_pitch(path)
        else:
            return 50.0, "Basic upload received. More analysis will be added."
    except Exception as e:
        return 40.0, f"Analysis failed: {str(e)}"

# --- Video pose analysis using MediaPipe & OpenCV
def analyze_video_pose(path, sample_rate=5):
    try:
        import cv2
        import mediapipe as mp
        mp_pose = mp.solutions.pose
        cap = cv2.VideoCapture(path)
        pose = mp_pose.Pose(static_image_mode=False, min_detection_confidence=0.5)
        angles = []
        frames = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frames += 1
            if frames % sample_rate != 0:
                continue
            image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = pose.process(image_rgb)
            if not res.pose_landmarks:
                continue
            lm = res.pose_landmarks.landmark
            # small helper to compute angle between 3 landmarks
            def angle(a,b,c):
                a = np.array([a.x,a.y,a.z])
                b = np.array([b.x,b.y,b.z])
                c = np.array([c.x,c.y,c.z])
                ba = a - b
                bc = c - b
                denom = (np.linalg.norm(ba)*np.linalg.norm(bc) + 1e-6)
                cos = np.dot(ba,bc)/denom
                cos = np.clip(cos, -1, 1)
                return np.degrees(np.arccos(cos))
            # example: left elbow angle
            try:
                left_elbow = angle(lm[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
                                   lm[mp_pose.PoseLandmark.LEFT_ELBOW.value],
                                   lm[mp_pose.PoseLandmark.LEFT_WRIST.value])
                right_elbow = angle(lm[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
                                    lm[mp_pose.PoseLandmark.RIGHT_ELBOW.value],
                                    lm[mp_pose.PoseLandmark.RIGHT_WRIST.value])
                angles.append((left_elbow + right_elbow) / 2.0)
            except Exception:
                continue
        cap.release()
        if not angles:
            return 30.0, "No clear full-body pose detected. Try framing whole body and good lighting."
        stability = max(0.0, 100.0 - np.std(angles))  # lower std = higher stability
        mean_angle_norm = (np.mean(angles) / 180.0) * 100.0
        score = float(np.clip(0.6 * stability + 0.4 * mean_angle_norm, 0, 100))
        feedback = f"Pose stability {stability:.1f}. Avg limb angle {np.mean(angles):.1f}deg."
        return round(score,2), feedback
    except Exception as e:
        return 40.0, f"Video analysis error: {e}"

# --- Audio pitch analysis using librosa
def analyze_audio_pitch(path):
    try:
        import librosa
        y, sr = librosa.load(path, sr=None, mono=True)
        # use librosa.pyin or piptrack
        try:
            f0, voiced_flag, voiced_prob = librosa.pyin(y, fmin=librosa.note_to_hz('C2'),
                                                         fmax=librosa.note_to_hz('C7'))
            freqs = f0[~np.isnan(f0)]
        except Exception:
            pitches, mags = librosa.piptrack(y=y, sr=sr)
            freqs = []
            for i in range(pitches.shape[1]):
                idx = mags[:,i].argmax()
                p = pitches[idx, i]
                if p > 0:
                    freqs.append(p)
            freqs = np.array(freqs) if freqs else np.array([])
        if freqs.size == 0:
            return 30.0, "No clear pitch detected. Try quieter environment and a close mic."
        mean_f = np.mean(freqs)
        std_f = np.std(freqs)
        stability_score = np.clip(100 - std_f * 0.5, 0, 100)
        energy = np.mean(np.abs(y))
        energy_score = np.clip(min(100, energy * 1000), 0, 100)
        score = round(0.65 * stability_score + 0.35 * energy_score, 2)
        feedback = f"Pitch stability std={std_f:.1f}Hz. Mean freq {mean_f:.1f}Hz."
        return float(score), feedback
    except Exception as e:
        return 40.0, f"Audio analysis error: {e}"
