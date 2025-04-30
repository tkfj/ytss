#!/bin/bash
# set -x
set -e

python src/preprocess.py
python src/ytss.py
