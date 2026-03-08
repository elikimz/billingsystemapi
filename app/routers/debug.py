from fastapi import APIRouter

router = APIRouter(prefix="/debug", tags=["Debug"])

@router.get("/error")
async def trigger_error():
    raise ValueError("This is a test error for the custom error handler")
