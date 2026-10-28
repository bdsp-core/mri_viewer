#!/bin/bash
# Run FreeBrowse on the server for the BIND 10-diagnosis cases (see serve_freebrowse.py). Listens on all interfaces, port 8765,
# for reviewers on the internal network / VPN:  http://<server>:8765/   (not exposed to the internet)
FB=${FREEBROWSE:-$HOME/Documents/EEG_report/freebrowse}
export FREEBROWSE=$FB NIIVUE_BUILD_DIR=$FB/frontend/dist DATA_DIR=/data/imaging_test/bind_10dx/viz REVIEW_DIR=/data/imaging_test/bind_10dx/review \
  AI_DIR=/data/imaging_test/bind_10dx/ai-sessions MODELS_DIR=$FB/models ENABLE_AI=false SCENE_SCHEMA_ID=freebrowse \
  IMAGING_EXTENSIONS='["*.nii", "*.nii.gz"]' SERVERLESS_MODE=false
cd "$(dirname "$0")" || exit 1
exec $HOME/.pixi/bin/pixi run --manifest-path $FB/backend/pixi.toml uvicorn serve_freebrowse:app --host 0.0.0.0 --port 8765
