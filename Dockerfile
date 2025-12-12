FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y curl git ripgrep jq python3 && rm -rf /var/lib/apt/lists/*

# Install Claude Code
RUN curl -fsSL https://claude.ai/install.sh | bash

WORKDIR /workspace

# Create .claude dir (configs mounted via docker-compose)
RUN mkdir -p /root/.claude/hooks

# Add claude to PATH
ENV PATH="/root/.local/bin:$PATH"

CMD ["/bin/bash"]
