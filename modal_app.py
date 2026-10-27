import modal

app = modal.App("lensalabel-backend")

image = modal.Image.from_dockerfile(
    "backend/Dockerfile",
    context_dir="backend",
)

@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name(
            "lensalabel-prod",
            required_keys=["DATABASE_URL"],
        )
    ],
    cpu=2,
    memory=4096,
    timeout=300,
    max_containers=1,
    scaledown_window=300,
)
@modal.asgi_app()
def web():
    from app.main import app as fastapi_app
    return fastapi_app