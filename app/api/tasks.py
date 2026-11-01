from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import Project, ProjectMember, Task, TaskStatusHistory, User
from app.models.enums import TaskPriority, TaskStatus
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.services.project_access import (
    NOT_ENOUGH_PERMISSIONS,
    PROJECT_NOT_FOUND,
    Permission,
    get_project_or_error,
)

router = APIRouter(prefix="/projects/{project_id}/tasks", tags=["tasks"])

MAX_INT32 = 2_147_483_647
ProjectId = Annotated[int, Path(ge=1, le=MAX_INT32)]
TaskId = Annotated[int, Path(ge=1, le=MAX_INT32)]
AssigneeFilter = Annotated[int | None, Query(ge=1, le=MAX_INT32)]

TASK_NOT_FOUND = "Task not found"
ASSIGNEE_FILTER_CONFLICT = "assignee_id cannot be combined with unassigned=true"

ASSIGNEE_NOT_FOUND = "Assignee not found"
ASSIGNEE_NOT_ALLOWED = "User cannot be assigned to this project"

_UNAUTHORIZED = {"description": "Токен отсутствует, недействителен или просрочен"}
_PROJECT_NOT_FOUND = {
    "description": "Проект не найден или у пользователя нет к нему доступа",
    "content": {"application/json": {"example": {"detail": PROJECT_NOT_FOUND}}},
}
_FORBIDDEN = {
    "description": "Недостаточно прав для создания задачи",
    "content": {"application/json": {"example": {"detail": NOT_ENOUGH_PERMISSIONS}}},
}


async def _ensure_assignee(db: DbSession, project: Project, assignee_id: int | None) -> None:
    if assignee_id is None:
        return
    user = await db.get(User, assignee_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ASSIGNEE_NOT_FOUND)
    if not user.is_active or not await _is_project_participant(db, project, user.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ASSIGNEE_NOT_ALLOWED)


async def _is_project_participant(db: DbSession, project: Project, user_id: int) -> bool:
    if project.owner_id == user_id:
        return True
    membership = await db.get(ProjectMember, (project.id, user_id))
    return membership is not None


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN: _FORBIDDEN,
        status.HTTP_404_NOT_FOUND: _PROJECT_NOT_FOUND,
        status.HTTP_409_CONFLICT: {
            "description": "Пользователя нельзя назначить исполнителем",
            "content": {"application/json": {"example": {"detail": ASSIGNEE_NOT_ALLOWED}}},
        },
    },
)
async def create_task(
    project_id: ProjectId,
    payload: TaskCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> Task:
    project = await get_project_or_error(
        db, project_id, current_user, required=Permission.CONTRIBUTE
    )
    await _ensure_assignee(db, project, payload.assignee_id)

    task = Task(
        title=payload.title,
        description=payload.description,
        status=TaskStatus.TODO,
        priority=payload.priority,
        due_date=payload.due_date,
        project_id=project.id,
        author_id=current_user.id,
        assignee_id=payload.assignee_id,
    )
    db.add(task)
    await db.flush()
    db.add(
        TaskStatusHistory(
            task_id=task.id,
            old_status=None,
            new_status=TaskStatus.TODO,
            changed_by_id=current_user.id,
        )
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(task)
    return task


@router.get(
    "",
    response_model=list[TaskResponse],
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND: _PROJECT_NOT_FOUND,
    },
)
async def list_tasks(
    project_id: ProjectId,
    current_user: CurrentUser,
    db: DbSession,
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority: TaskPriority | None = None,
    assignee_id: AssigneeFilter = None,
    unassigned: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Task]:
    project = await get_project_or_error(db, project_id, current_user, required=Permission.READ)
    if unassigned and assignee_id is not None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=ASSIGNEE_FILTER_CONFLICT)

    query = select(Task).where(Task.project_id == project.id)
    if status_filter is not None:
        query = query.where(Task.status == status_filter)
    if priority is not None:
        query = query.where(Task.priority == priority)
    if unassigned:
        query = query.where(Task.assignee_id.is_(None))
    elif assignee_id is not None:
        query = query.where(Task.assignee_id == assignee_id)
    result = await db.execute(query.order_by(Task.id.desc()).limit(limit).offset(offset))
    return list(result.scalars().all())


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND: {
            "description": "Нет доступа к проекту (Project not found) или задача не в этом проекте (Task not found)",
            "content": {"application/json": {"example": {"detail": TASK_NOT_FOUND}}},
        },
    },
)
async def get_task(
    project_id: ProjectId,
    task_id: TaskId,
    current_user: CurrentUser,
    db: DbSession,
) -> Task:
    project = await get_project_or_error(db, project_id, current_user, required=Permission.READ)
    task = await db.get(Task, task_id)
    if task is None or task.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=TASK_NOT_FOUND)
    return task


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав для изменения задачи",
            "content": {"application/json": {"example": {"detail": NOT_ENOUGH_PERMISSIONS}}},
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Нет доступа к проекту (Project not found) или задача не в этом проекте (Task not found)",
            "content": {"application/json": {"example": {"detail": TASK_NOT_FOUND}}},
        },
        status.HTTP_409_CONFLICT: {
            "description": "Пользователя нельзя назначить исполнителем",
            "content": {"application/json": {"example": {"detail": ASSIGNEE_NOT_ALLOWED}}},
        },
    },
)
async def update_task(
    project_id: ProjectId,
    task_id: TaskId,
    payload: TaskUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> Task:
    project = await get_project_or_error(
        db, project_id, current_user, required=Permission.CONTRIBUTE
    )
    task = await db.get(Task, task_id)
    if task is None or task.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=TASK_NOT_FOUND)

    changes = payload.model_dump(exclude_unset=True)
    if "assignee_id" in changes and changes["assignee_id"] is not None:
        await _ensure_assignee(db, project, changes["assignee_id"])

    previous_status = task.status
    for field, value in changes.items():
        setattr(task, field, value)
    if "status" in changes and changes["status"] != previous_status:
        db.add(
            TaskStatusHistory(
                task_id=task.id,
                old_status=previous_status,
                new_status=changes["status"],
                changed_by_id=current_user.id,
            )
        )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(task)
    return task
