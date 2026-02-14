"""
Session REST Endpoints
=======================
CRUD operations for sessions via REST API.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.db.connection import get_connection
from app.db.repositories import session_repo


router = APIRouter(tags=["sessions"])


class CreateSessionRequest(BaseModel):
    """Request model for creating a session."""
    mode_type: str  # "single" | "batch" | "grid_search"
    strategy_id: int = 1
    config_snapshot: Optional[dict] = None
    git_hash: Optional[str] = None
    notes: Optional[str] = None


class SessionResponse(BaseModel):
    """Response model for session data."""
    id: str
    mode_type: str
    strategy_id: int
    created_at: str
    last_accessed: Optional[str]
    status: str
    config_snapshot: dict
    git_hash: Optional[str]
    notes: Optional[str]


@router.post("/sessions", response_model=dict)
def create_session(req: CreateSessionRequest):
    """
    Create a new session.

    Returns:
        dict: {"session_id": "sess_..."}
    """
    with get_connection() as conn:
        session_id = session_repo.create_session(
            conn,
            req.mode_type,
            req.strategy_id,
            req.config_snapshot or {},
            req.git_hash,
            req.notes
        )
    return {"id": session_id, "session_id": session_id}


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    mode_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """
    List sessions with optional filters.

    Query params:
        mode_type: Filter by "single" or "batch"
        status: Filter by "active" or "archived"
        limit: Max results (default 50)
        offset: Pagination offset (default 0)

    Returns:
        list[SessionResponse]: List of sessions
    """
    with get_connection() as conn:
        sessions = session_repo.list_sessions(
            conn,
            mode_type=mode_type,
            status=status,
            limit=limit,
            offset=offset
        )
    return sessions


@router.get("/sessions/current")
def get_current_session():
    """
    Get the most recent active session, or 404 if none exists.
    Used by UI to auto-attach to an existing session.
    """
    with get_connection() as conn:
        sessions = session_repo.list_sessions(conn, status="active", limit=1)

    if not sessions:
        raise HTTPException(status_code=404, detail="No active session found")

    return sessions[0]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str):
    """
    Get a single session by ID.

    Args:
        session_id: Session ID to retrieve

    Returns:
        SessionResponse: Session data

    Raises:
        HTTPException: 404 if session not found
    """
    with get_connection() as conn:
        session = session_repo.get_session(conn, session_id)

    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return session


@router.patch("/sessions/{session_id}/archive", response_model=dict)
def archive_session(session_id: str):
    """
    Archive a session (set status to 'archived').

    Args:
        session_id: Session ID to archive

    Returns:
        dict: {"success": true}

    Raises:
        HTTPException: 404 if session not found
    """
    with get_connection() as conn:
        success = session_repo.archive_session(conn, session_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return {"success": True}


@router.delete("/sessions/{session_id}", response_model=dict)
def delete_session(session_id: str):
    """
    Delete a session and all related data (cascade).
    Used by cleanup policy.

    Args:
        session_id: Session ID to delete

    Returns:
        dict: {"success": true}

    Raises:
        HTTPException: 404 if session not found
    """
    with get_connection() as conn:
        success = session_repo.delete_session(conn, session_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return {"success": True}
