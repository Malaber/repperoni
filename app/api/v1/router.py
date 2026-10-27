from fastapi import APIRouter

from app.api.v1.routes import auth, mobile_auth, workouts


router = APIRouter()
router.include_router(auth.router)
router.include_router(workouts.router)

router.include_router(mobile_auth.router)
