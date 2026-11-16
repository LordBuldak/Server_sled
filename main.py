import datetime
import os
import json
import hashlib
import numpy as np
from typing import Dict
from scipy.spatial import distance

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy import select, update, delete, func, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from init_db import (
    DATABASE_URL, Group, Student, Pris, Classroom, 
    Filter, AntiWebsite, AntiApp, Narush, Teacher
)

import face_recognition
from skimage import io as ios

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key=b'_5#y2L"F4Q8z\n\xec]/')
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

ADMIN_CREDENTIALS = {
    "username": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918",
    "password": "44ac9a7d1fed334c2d41c75d56e33e04857988f767ae4fccac6b6b1799dd8f80",
}

sp_days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Хранилище статусов распознавания лиц для кабинетов (classroom_id -> bool)
FACE_REC_STATUS: Dict[int, bool] = {}

async def get_db():
    async with async_session() as session:
        async with session.begin():
            await session.execute(text("PRAGMA foreign_keys = ON;"))
            yield session

def hash_func(s: str):
    return hashlib.sha256(s.encode()).hexdigest()

def allowed_file(filename: str):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"png", "jpg", "jpeg", "gif"}

def is_logged_in(request: Request):
    return request.session.get("is_login") is True

# Менеджер WebSocket соединений для передачи правил клиентам
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, hostname: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[hostname] = websocket

    def disconnect(self, hostname: str):
        if hostname in self.active_connections:
            del self.active_connections[hostname]

    async def send_rules(self, hostname: str, rules: dict):
        if hostname in self.active_connections:
            await self.active_connections[hostname].send_json(rules)

manager = ConnectionManager()

async def get_active_rules_for_host(hostname: str, db: AsyncSession):
    classrooms_res = await db.execute(select(Classroom.id).where(func.instr(hostname, Classroom.name) > 0))
    classroom_ids = classrooms_res.scalars().all()

    if not classroom_ids:
        return {"allowed_websites": [], "blocked_apps": [], "face_rec_enabled": True}

    c_id = classroom_ids[0]
    face_rec_enabled = FACE_REC_STATUS.get(c_id, True)

    filters_res = await db.execute(
        select(Filter.id).where(Filter.classroom_id.in_(classroom_ids), Filter.activate == 1)
    )
    filter_ids = filters_res.scalars().all()

    if not filter_ids:
        return {"allowed_websites": [], "blocked_apps": [], "face_rec_enabled": face_rec_enabled}

    # Белый список сайтов (block == 0 значит РАЗРЕШЕНО)
    sites_res = await db.execute(
        select(AntiWebsite.name_site).where(AntiWebsite.block == 0, AntiWebsite.id_filter.in_(filter_ids))
    )
    allowed_sites = list(sites_res.scalars().all())

    # Черный список приложений (block == 1 значит ЗАБЛОКИРОВАНО)
    apps_res = await db.execute(
        select(AntiApp.name_app).where(AntiApp.block == 1, AntiApp.id_filter.in_(filter_ids))
    )
    blocked_apps = list(apps_res.scalars().all())

    return {
        "allowed_websites": allowed_sites,
        "blocked_apps": blocked_apps,
        "face_rec_enabled": face_rec_enabled
    }

async def get_current_group_id(db: AsyncSession) -> int:
    today = datetime.datetime.now()
    weekday_str = str(today.weekday())
    current_time = today.time()

    res = await db.execute(select(Group))
    groups = res.scalars().all()

    for g in groups:
        if not g.rasp:
            continue
        try:
            rasp_dict = json.loads(g.rasp)
            if weekday_str in rasp_dict:
                time_range = rasp_dict[weekday_str].replace("–", "-")
                start_str, end_str = time_range.split("-")
                
                h1, m1 = map(int, start_str.split(":"))
                h2, m2 = map(int, end_str.split(":"))
                
                if datetime.time(h1, m1) <= current_time <= datetime.time(h2, m2):
                    return g.id
        except Exception:
            continue
    return 0

@app.websocket("/ws/client/{hostname}")
async def websocket_endpoint(websocket: WebSocket, hostname: str):
    await manager.connect(hostname, websocket)
    async with async_session() as db:
        rules = await get_active_rules_for_host(hostname, db)
        await websocket.send_json({"type": "rules", "data": rules})

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(hostname)

@app.post("/update-face-rec-status")
async def update_face_rec_status(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    classroom_id = data.get("classroom_id")
    is_enabled = data.get("face_rec_enabled", True)

    FACE_REC_STATUS[classroom_id] = is_enabled

    room_res = await db.execute(select(Classroom.name).where(Classroom.id == classroom_id))
    room_name = room_res.scalar_one_or_none()

    if room_name:
        for hostname in list(manager.active_connections.keys()):
            if room_name in hostname:
                rules = await get_active_rules_for_host(hostname, db)
                await manager.send_rules(hostname, {"type": "rules", "data": rules})

    return {"success": True}

@app.post("/match_student")
async def match_student(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.json()
    vector = payload.get("vector")
    item_name = payload.get("item_name", "Неизвестно")
    hostname = payload.get("hostname", "")

    if not vector:
        raise HTTPException(status_code=400, detail="Вектор отсутствует")

    group_id = await get_current_group_id(db)
    if group_id == 0:
        await record_unrecognized(item_name, hostname)
        return {"status": "unrecognized", "reason": "No active group"}

    students_res = await db.execute(select(Student.id, Student.name_student, Student.vector).where(Student.id_group == group_id))
    students = students_res.all()

    client_vec = np.array(vector, dtype=np.float64)
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    for s_id, s_name, s_vector in students:
        if s_vector:
            db_vec = np.frombuffer(s_vector, dtype=np.float64)
            if distance.euclidean(client_vec, db_vec) < 0.6:
                pris_res = await db.execute(select(Pris.id).where(Pris.student_id == s_id, Pris.data == today_str))
                pris_id = pris_res.scalar_one_or_none()
                
                if not pris_id:
                    new_pris = Pris(group_id=group_id, student_id=s_id, data=today_str)
                    db.add(new_pris)
                    await db.flush()
                    pris_id = new_pris.id

                new_narush = Narush(
                    anti_name=item_name,
                    id_student=s_id,
                    time=datetime.datetime.now().strftime("%H:%M"),
                    id_pris=pris_id,
                    group_id=group_id
                )
                db.add(new_narush)
                return {"status": "matched", "student_name": s_name}

    await record_unrecognized(item_name, hostname)
    return {"status": "unrecognized"}

async def record_unrecognized(item_name: str, hostname: str):
    today = datetime.date.today().strftime("%Y-%m-%d")
    now_time = datetime.datetime.now().strftime("%H:%M")
    
    try:
        with open("data.json", "r", encoding="utf-8") as f:
            records = json.load(f)
        if not isinstance(records, list):
            records = [[0]]
    except Exception:
        records = [[0]]

    new_id = max([r[0] for r in records if isinstance(r, list) and len(r) > 0] or [0]) + 1
    new_record = [new_id, item_name, hostname, today, now_time]
    records.append(new_record)

    cutoff_str = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    records = [r for r in records if len(r) >= 4 and isinstance(r[3], str) and r[3] >= cutoff_str]

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

# ==================== ВЕБ-ИНТЕРФЕЙС И МАРШРУТЫ ====================

@app.get("/")
async def glav(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "glav.html", {"admin": request.session.get("is_admin") is not None})

@app.get("/login")
async def login_get(request: Request):
    return templates.TemplateResponse(request, "login.html")

@app.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    teacher_res = await db.execute(select(Teacher).where(Teacher.login == username, Teacher.password == hash_func(password)))
    teacher = teacher_res.scalar_one_or_none()

    if hash_func(username) == ADMIN_CREDENTIALS["username"] and hash_func(password) == ADMIN_CREDENTIALS["password"]:
        request.session["is_login"] = True
        request.session["is_admin"] = True
        return RedirectResponse(url="/", status_code=303)
    elif teacher is not None:
        request.session["is_login"] = True
        return RedirectResponse(url="/", status_code=303)
    else:
        return templates.TemplateResponse(request, "login.html", {"error": "Неверный логин или пароль"})

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/groups")
async def index_groups(request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    
    result = await db.execute(select(Group))
    groups = result.scalars().all()
    return templates.TemplateResponse(request, "index.html", {
        "groups": groups, 
        "admin": request.session.get("is_admin") is not None
    })

@app.get("/add-group")
async def add_group_get(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "add_group.html")

@app.post("/add-group")
async def add_group_post(request: Request, group_name: str = Form(...), schedule: str = Form(...), db: AsyncSession = Depends(get_db)):
    sched_list = json.loads(schedule)
    dict_rasp = {}
    for i in sched_list:
        dict_rasp.update({str(sp_days.index(i["day"])): f"{i['start']}-{i['end']}"})

    new_group = Group(groups_name=group_name, rasp=json.dumps(dict_rasp))
    db.add(new_group)
    return RedirectResponse(url="/groups", status_code=303)

@app.get("/schedule/{group_id}")
async def group_rasp(group_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    schedule_dict = json.loads(group.rasp) if group.rasp else {}
    return templates.TemplateResponse(request, "rasp_group.html", {
        "group_name": group.groups_name,
        "id_group": group_id,
        "schedule_dict": schedule_dict,
    })

@app.post("/update_schedule/{id_group}")
async def update_schedule(id_group: int, request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)

    form_data = await request.form()
    schedule = {}
    for day in ["0", "1", "2", "3", "4", "5", "6"]:
        t = form_data.get(f"time_{day}")
        if t and str(t).strip():
            schedule[day] = str(t).strip()

    await db.execute(update(Group).where(Group.id == id_group).values(rasp=json.dumps(schedule)))
    return RedirectResponse(url=f"/schedule/{id_group}", status_code=303)

@app.get("/group/{id_group}")
async def pris_view(id_group: int, request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)

    group_res = await db.execute(select(Group.groups_name).where(Group.id == id_group))
    group_name = group_res.scalar_one_or_none()
    if not group_name:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    dates_res = await db.execute(select(Pris.data).where(Pris.group_id == id_group).distinct())
    dates = sorted([d for d in dates_res.scalars().all() if d])

    students_res = await db.execute(select(Student.id, Student.name_student).where(Student.id_group == id_group))
    students = students_res.all()

    pris_res = await db.execute(select(Pris.student_id, Pris.data).where(Pris.group_id == id_group))
    attendance = set(pris_res.all())

    violations_res = await db.execute(
        select(Narush.anti_name, Narush.id_student, Narush.time, Pris.data)
        .join(Pris, Narush.id_pris == Pris.id)
        .where(Pris.group_id == id_group)
    )

    violations_dict = {}
    for anti_name, student_id, v_time, date_val in violations_res.all():
        key = (student_id, date_val)
        if key not in violations_dict:
            violations_dict[key] = []
        violations_dict[key].append({"time": v_time, "description": anti_name})

    res = []
    try:
        with open("data.json", encoding="utf-8") as f:
            all_unrecognized = json.load(f)
        cutoff_str = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        res = [i for i in all_unrecognized if len(i) >= 3 and i[3] >= cutoff_str]
    except Exception:
        pass

    return templates.TemplateResponse(request, "table_pris.html", {
        "group_name": group_name,
        "dates": dates,
        "students": students,
        "attendance": attendance,
        "violations": violations_dict,
        "unrecognized_today": res,
        "id_group": id_group,
        "admin": request.session.get("is_admin") is not None,
    })

@app.get("/add_student/{id_group}")
async def add_student_get(id_group: int, request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "add_student.html", {"id_group": id_group})

@app.post("/add_student/{id_group}")
async def add_student_post(
    id_group: int, 
    student_name: str = Form(...), 
    photo: UploadFile = File(...), 
    db: AsyncSession = Depends(get_db)
):
    name = student_name.strip()
    if not name or not photo.filename or not allowed_file(photo.filename):
        raise HTTPException(status_code=400, detail="Недопустимые параметры или файл")

    photo_bytes = await photo.read()
    try:
        img = ios.imread(io.BytesIO(photo_bytes))
        face_encodings = face_recognition.face_encodings(img)
        if len(face_encodings) == 0:
            raise HTTPException(status_code=400, detail="Лицо не найдено на фотографии")
        embedding = face_encodings[0].tobytes()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка обработки изображения: {str(e)}")

    new_student = Student(name_student=name, vector=embedding, id_group=id_group)
    db.add(new_student)
    return {"success": True}

@app.post("/delete_student/{student_id}")
async def delete_student(student_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Student).where(Student.id == student_id))
    return RedirectResponse(url="/groups", status_code=303)

@app.post("/delete_group/{id_group}")
async def delete_group(id_group: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Group).where(Group.id == id_group))
    return RedirectResponse(url="/groups", status_code=303)

@app.get("/classrooms")
async def classrooms(request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    res = await db.execute(select(Classroom))
    return templates.TemplateResponse(request, "classrooms.html", {"classrooms": res.scalars().all()})

@app.get("/new_classroom")
async def new_classroom_get(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "add_classroom.html")

@app.post("/new_classroom")
async def new_classroom_post(name: str = Form(...), db: AsyncSession = Depends(get_db)):
    new_room = Classroom(name=name)
    db.add(new_room)
    await db.flush()
    return RedirectResponse(url=f"/filter/{new_room.id}", status_code=303)

@app.get("/filter/{classroom_id}")
async def filters(classroom_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)

    filters_res = await db.execute(select(Filter).where(Filter.classroom_id == classroom_id))
    room_res = await db.execute(select(Classroom.name).where(Classroom.id == classroom_id))

    return templates.TemplateResponse(request, "filters.html", {
        "data": filters_res.scalars().all(), 
        "name": room_res.scalar_one_or_none(), 
        "id": classroom_id
    })

@app.post("/update-filter-status")
async def update_filter_status(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    await db.execute(update(Filter).where(Filter.id == data.get("id")).values(activate=data.get("is_active")))
    return {"success": True}

@app.get("/protiv/{filter_id}")
async def protiv_get(filter_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)

    apps_res = await db.execute(select(AntiApp).where(AntiApp.id_filter == filter_id))
    sites_res = await db.execute(select(AntiWebsite).where(AntiWebsite.id_filter == filter_id))
    f_res = await db.execute(select(Filter.name_filter).where(Filter.id == filter_id))

    return templates.TemplateResponse(request, "protiv.html", {
        "anti_app": apps_res.scalars().all(),
        "anti_website": sites_res.scalars().all(),
        "name": f_res.scalar_one_or_none(),
        "id": filter_id,
    })

@app.post("/protiv/{filter_id}")
async def protiv_post(filter_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    for app_item in data.get("anti_app", []):
        await db.execute(update(AntiApp).where(AntiApp.id == app_item["id"]).values(block=app_item["state"]))
    for site_item in data.get("anti_website", []):
        await db.execute(update(AntiWebsite).where(AntiWebsite.id == site_item["id"]).values(block=site_item["state"]))
    return {"message": "Успешно сохранено!"}

@app.get("/teachers")
async def teachers_view(request: Request, db: AsyncSession = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    res = await db.execute(select(Teacher.id, Teacher.name_teacher))
    return templates.TemplateResponse(request, "teachers.html", {"teachers": res.all()})

@app.get("/latest_violations/{group_id}")
async def latest_violations(group_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Student.name_student, Narush.time, Narush.anti_name)
        .join(Student, Narush.id_student == Student.id)
        .where(Narush.group_id == group_id)
    )
    rows = res.all()
    data = [[r[0], r[1], r[2]] for r in rows[-3:][::-1]]
    return data

@app.get("/unrecognized_today")
async def unrecognized_today_api():
    res = []
    try:
        with open("data.json", encoding="utf-8") as f:
            all_unrecognized = json.load(f)
        cutoff_str = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        res = [i for i in all_unrecognized if len(i) >= 3 and i[3] >= cutoff_str]
        with open("data.json", encoding="utf-8", mode="w") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return res

@app.get("/add_teachers")
async def add_teach_get(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "add_teachers.html")

@app.post("/add_teachers")
async def add_teach_post(request: Request, full_name: str = Form(...), login: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    db.add(Teacher(login=login, password=hash_func(password), name_teacher=full_name))
    return RedirectResponse(url="/", status_code=303)