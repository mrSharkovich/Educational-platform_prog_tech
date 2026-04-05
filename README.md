# EduPath

Образовательная веб-платформа с разделением ролей **студент / преподаватель**, построенная на Flask + SQLite + Vanilla JS.

> Курсы → блоки → уроки и задания. Преподаватели создают контент, студенты проходят его и получают обратную связь.

---

## Содержание

- [Быстрый старт](#быстрый-старт)
- [Стек технологий](#стек-технологий)
- [Структура проекта](#структура-проекта)
- [Возможности](#возможности)
- [Тестовые аккаунты](#тестовые-аккаунты)
- [Конфигурация](#конфигурация)
- [API — Краткий справочник](#api--краткий-справочник)
- [База данных](#база-данных)

---

## Быстрый старт

**Требования:** Python 3.10+, pip


#### 1. Распаковать проект

#### 2. Установить зависимости
```bash
pip install -r requirements.txt
```

#### 3. Запустить

```bash
python src\backend\app.py
```

Приложение доступно по адресу: **http://localhost:5000**

При первом запуске автоматически создаётся БД, применяются миграции и добавляются тестовые данные.

---

## Стек технологий

| Слой | Технология | Версия |
|------|-----------|--------|
| Backend | Python + Flask | 3.10+ / 3.0+ |
| База данных | SQLite | встроен в Python |
| Шаблоны | Jinja2 | встроен в Flask |
| Frontend | Vanilla JS (ES2020+) | — |
| CSS | Custom Properties, без фреймворков | — |
| Шрифты | Syne, DM Sans | Google Fonts |

Нет ORM. Нет npm. Нет сборщиков. Только Python и браузер.

---

## Структура проекта

```
Educational-platform_prog_tech/src
├── backend/
│   ├── app.py               # Flask-приложение: маршруты, API, логика, инициализация БД
│   ├── database.py          # Подключение к SQLite через контекст приложения Flask
│   └── requirements.txt     # Python-зависимости (только flask)
│
├── frontend/
│   ├── static/
│   │   ├── css/
│   │   │   ├── style.css        # Дизайн-система студенческого интерфейса
│   │   │   └── teacher.css      # Стили кабинета преподавателя
│   │   └── js/
│   │       └── utils.js         # Утилиты: api.get/post, toast, btnLoad
│   └── templates/
│       ├── base.html            # Базовый шаблон студента (навбар, модали)
│       ├── index.html           # Главная страница (лендинг)
│       ├── login.html           # Вход студента
│       ├── register.html        # Регистрация студента
│       ├── catalog.html         # Каталог курсов
│       ├── dashboard.html       # Кабинет студента
│       ├── course.html          # Прохождение курса
│       └── teacher/
│           ├── base.html            # Базовый шаблон преподавателя
│           ├── login.html           # Вход преподавателя
│           ├── register.html        # Регистрация преподавателя
│           ├── dashboard.html       # Кабинет преподавателя
│           ├── course_manage.html   # Управление курсом
│           ├── builder.html         # Конструктор курсов
│           ├── students.html        # Список студентов
│           ├── requests.html        # Заявки на курсы
│           └── catalog_view.html    # Каталог (вид преподавателя)
│
├── .gitignore
├── LICENSE
├── README.md
└── requirements.txt
```

---

## Возможности

### Студент
- Регистрация и вход; каталог открытых и закрытых курсов
- Заявка на закрытый курс; повторная заявка после отклонения
- Прохождение уроков (текст + YouTube/PDF материалы)
- 5 типов заданий: развёрнутый, краткий, тест, видео, PDF
- Автопроверка краткого ответа и теста; ручная проверка преподавателем
- Лимит попыток; повтор задания при неверном ответе
- Прогресс курса; комментарии преподавателя к ответам

### Преподаватель
- Конструктор курсов: блоки → уроки и задания любых типов
- Настройка правильного ответа и лимита попыток для каждого задания
- Проверка развёрнутых ответов: принять / отклонить + комментарий
- История комментариев по каждому ответу студента
- Управление студентами: прогресс, отчисление
- Заявки: одобрение/отклонение с уведомлением студента
- Статистика с красными точками на непроверенных заданиях
- Удаление курса с подтверждением

---


## Конфигурация

| Параметр | Значение по умолчанию | Где задаётся |
|---------|-----------------------|-------------|
| Секретный ключ | `'dev'` | `app.secret_key` в `app.py` |
| Путь к БД | `instance/learning_platform.db` | `app.config['DATABASE']` |
| Порт | `5000` | `app.run(port=5000)` |
| Режим отладки | `True` | `app.run(debug=True)` |


---

## API — Краткий справочник



```
# Аутентификация
POST /api/register                    Регистрация студента
POST /api/login                       Вход студента
POST /api/teacher/register            Регистрация преподавателя
POST /api/teacher/login               Вход преподавателя

# Каталог
GET  /api/catalog/open                Открытые курсы
POST /api/catalog/search              Поиск закрытого курса + заявка
POST /api/catalog/reapply/<id>        Повторная заявка
POST /api/catalog/enroll/<id>         Запись на открытый курс

# Курсы преподавателя
GET|POST        /api/teacher/courses
PUT|DELETE      /api/teacher/courses/<id>
GET|POST        /api/teacher/courses/<id>/blocks
PUT|DELETE      /api/teacher/blocks/<id>
POST            /api/teacher/blocks/<id>/items/lesson
POST            /api/teacher/blocks/<id>/items/task
PUT             /api/teacher/items/lesson/<id>
PUT             /api/teacher/items/task/<id>
DELETE          /api/teacher/items/<id>

# Проверка
GET  /api/teacher/courses/<id>/homework
POST /api/teacher/homework/<id>/review
GET  /api/teacher/homework/<id>/history

# Студенты и заявки
GET    /api/teacher/students
GET    /api/teacher/all-requests
DELETE /api/teacher/courses/<id>/students/<uid>
POST   /api/teacher/requests/<id>/approve
POST   /api/teacher/requests/<id>/reject

# Прохождение курса
GET  /api/courses/<id>/sections
GET  /api/lessons/<id>
GET  /api/tasks/<id>
POST /api/tasks/<id>/answer
GET  /api/user/progress
```

---

## База данных


| Группа | Таблицы |
|--------|---------|
| Пользователи | `users`, `teachers` |
| Курсы | `courses`, `course_blocks`, `block_items`, `lessons`, `lesson_materials`, `tasks` |
| Прогресс | `task_answers`, `task_attempts`, `user_progress`, `homework_answers` |
| Комментарии | `comments`, `answer_comments` |
| Доступ | `user_courses`, `course_requests` |

---


