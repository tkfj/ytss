FROM python:3.13-slim-bullseye
# bookwormだとffmpegがsegmentエラーでcore吐いて落ちる

ARG USERNAME=appuser
ARG USER_UID=1000
ARG USER_GID=${USER_UID}

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        sudo \
        locales \
        build-essential \
        openssh-client \
        git ca-certificates gnupg \
    && rm -rf /var/lib/apt/lists/*

RUN locale-gen --lang C.UTF-8

ENV LANG C.UTF-8
ENV LANGUAGE C
ENV LC_ALL C.UTF-8
ENV TZ Asia/Tokyo
ENV DEBIAN_FRONTEND=noninteractive

RUN groupadd --gid ${USER_GID} ${USERNAME} \
  && useradd -m --shell /bin/bash --uid ${USER_UID} --gid ${USER_GID} ${USERNAME} \
  && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

RUN echo "alias ll='ls -alF'" >> /etc/bash.bashrc && \
    echo "alias la='ls -A'" >> /etc/bash.bashrc && \
    echo "alias l='ls -CF'" >> /etc/bash.bashrc

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && \
    chmod a+rx /usr/local/bin/yt-dlp && \
    cd /tmp && \
    curl -LO https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz && \
    tar xvf ffmpeg-release-amd64-static.tar.xz && \
    cd ffmpeg-*-amd64-static && \
    cp ffmpeg /usr/local/bin/ && \
    cp ffprobe /usr/local/bin/

RUN pip install --no-cache-dir \
    Pillow \
    PyYAML \
    requests

WORKDIR /usr/src/app
USER ${USERNAME}
