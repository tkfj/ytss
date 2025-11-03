FROM python:3.13-slim-bullseye
# bookwormだとffmpegがsegmentエラーでcore吐いて落ちる

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        sudo \
        locales \
        build-essential \
        git ca-certificates gnupg \
        curl \
        jq \
        && rm -rf /var/lib/apt/lists/*

RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && \
    chmod a+rx /usr/local/bin/yt-dlp && \
    cd /tmp && \
    curl -LO https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz && \
    tar xvf ffmpeg-release-amd64-static.tar.xz && \
    cd ffmpeg-*-amd64-static && \
    cp ffmpeg /usr/local/bin/ && \
    cp ffprobe /usr/local/bin/

RUN sed -i -E 's/# (en_US.UTF-8)/\1/' /etc/locale.gen \
    && locale-gen

ENV LANG en_US.UTF-8
ENV LANGUAGE en_US
ENV LC_ALL en_US.UTF-8
ENV TZ Asia/Tokyo
ENV DEBIAN_FRONTEND=noninteractive


RUN pip install --no-cache-dir \
    Pillow \
    PyYAML \
    requests

    WORKDIR /usr/src/app

ARG USERNAME=appuser
ARG USER_UID=1000
ARG USER_GID=${USER_UID}

RUN groupadd --gid ${USER_GID} ${USERNAME} \
  && useradd -m --shell /bin/bash --uid ${USER_UID} --gid ${USER_GID} ${USERNAME} \
  && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

RUN echo "alias ll='ls -alF'" >> /etc/bash.bashrc && \
    echo "alias la='ls -A'" >> /etc/bash.bashrc && \
    echo "alias l='ls -CF'" >> /etc/bash.bashrc
