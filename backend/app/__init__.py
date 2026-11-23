"""AXON: asistente educativo local con permisos independientes del modelo."""
import os

# This must precede importing ONNX Runtime; its API switch alone runs after initialization.
os.environ['ORT_DISABLE_TELEMETRY']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
