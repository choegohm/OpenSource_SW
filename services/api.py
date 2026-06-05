from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import json
import os
import time
import threading
from services.llm import analyze_intent

app = FastAPI(title="EnvCraft API")

# 사용자별 port-forward 포트 관리
port_registry: dict[str, int] = {}
port_counter = 8900

def get_or_assign_port(user_id: str) -> int:
    global port_counter
    if user_id not in port_registry:
        port_registry[user_id] = port_counter
        port_counter += 1
    return port_registry[user_id]

def wait_for_pod(user_id: str, timeout: int = 120) -> str | None:
    """Pod이 Running 상태가 될 때까지 대기 후 Pod 이름 반환"""
    start = time.time()
    while time.time() - start < timeout:
        result = subprocess.run(
            ["kubectl", "get", "pods", "-n", "workspaces",
             "--field-selector=status.phase=Running",
             "-o", "jsonpath={.items[*].metadata.name}"],
            capture_output=True, text=True
        )
        pods = result.stdout.strip().split()
        for pod in pods:
            if user_id in pod:
                return pod
        time.sleep(3)
    return None

def start_port_forward(pod_name: str, local_port: int):
    """별도 스레드에서 port-forward 실행"""
    def run():
        subprocess.run(
            ["kubectl", "port-forward",
             "-n", "workspaces",
             f"pod/{pod_name}",
             f"{local_port}:8080"],
            capture_output=True
        )
    thread = threading.Thread(target=run, daemon=True)
    thread.start()

class EnvironmentRequest(BaseModel):
    user_input: str
    user_id: str = "user1"

class EnvironmentResponse(BaseModel):
    status: str
    user_id: str
    config: dict
    message: str
    url: str

@app.get("/")
def root():
    return {"message": "EnvCraft API 서버가 실행 중입니다!"}

@app.post("/generate", response_model=EnvironmentResponse)
async def generate_environment(request: EnvironmentRequest):

    # Step 1 - LLM으로 JSON 생성
    try:
        config = analyze_intent(request.user_input)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 분석 실패: {str(e)}")

    # Step 2 - Argo 파이프라인 트리거
    try:
        argo_cmd = [
            "argo", "submit",
            f"--from=workflowtemplate/devspace-pipeline",
            "--from", "workflowtemplate/devspace-pipeline",
            "-n", "argo",
            "--parameter", f"userId={request.user_id}",
            "--parameter", f"image={config['image']}",
            "--parameter", f"cpu={config['cpu']}",
            "--parameter", f"memory=1Gi",
        ]
        result = subprocess.run(argo_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Argo 파이프라인 실행 실패: {str(e)}")

    # Step 3 - Pod Running 대기
    pod_name = wait_for_pod(request.user_id, timeout=120)
    if not pod_name:
        raise HTTPException(status_code=500, detail="Pod 시작 시간 초과 (120초). 잠시 후 다시 시도해주세요.")

    # Step 4 - port-forward 자동 실행
    local_port = get_or_assign_port(request.user_id)
    start_port_forward(pod_name, local_port)
    time.sleep(2)

    access_url = f"http://localhost:{local_port}"

    return EnvironmentResponse(
        status="success",
        user_id=request.user_id,
        config=config,
        message=f"개발환경이 준비되었습니다! 비밀번호: devspace1234",
        url=access_url
    )

@app.get("/status/{user_id}")
async def get_status(user_id: str):
    try:
        result = subprocess.run(
            ["kubectl", "get", "ksvc", f"ws-{user_id}", "-n", "workspaces"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return {"status": "not_found", "user_id": user_id}

        local_port = port_registry.get(user_id)
        return {
            "status": "running",
            "user_id": user_id,
            "url": f"http://localhost:{local_port}" if local_port else "포트 미할당"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi.responses import FileResponse

@app.get("/ui")
def serve_ui():
    return FileResponse(os.path.join(os.path.dirname(os.path.dirname(__file__)), "index.html"))