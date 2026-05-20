from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import json
import os
from services.llm import analyze_intent

app = FastAPI(title="DevSpace AI API")

class EnvironmentRequest(BaseModel):
    user_input: str
    user_id: str = "user1"

class EnvironmentResponse(BaseModel):
    status: str
    user_id: str
    config: dict
    message: str

@app.get("/")
def root():
    return {"message": "DevSpace AI API 서버가 실행 중입니다!"}

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
            "--from", "workflowtemplate/devspace-pipeline",
            "-n", "argo",
            "-p", f"userId={request.user_id}",
            "-p", f"image={config['image']}",
            "-p", f"cpu={config['cpu']}",
            "-p", f"memory={config['memory']}",
        ]
        result = subprocess.run(
            argo_cmd,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise Exception(result.stderr)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Argo 파이프라인 실행 실패: {str(e)}")

    return EnvironmentResponse(
        status="success",
        user_id=request.user_id,
        config=config,
        message=f"개발환경 생성 중입니다! 접속 URL: ws-{request.user_id}.workspaces.svc.cluster.local"
    )

@app.get("/status/{user_id}")
async def get_status(user_id: str):
    try:
        result = subprocess.run(
            ["kubectl", "get", "ksvc", f"ws-{user_id}", "-n", "workspaces"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return {"status": "not_found", "user_id": user_id}

        return {
            "status": "running",
            "user_id": user_id,
            "url": f"ws-{user_id}.workspaces.svc.cluster.local"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi.responses import FileResponse
import os

@app.get("/ui")
def serve_ui():
    return FileResponse(os.path.join(os.path.dirname(os.path.dirname(__file__)), "index.html"))
