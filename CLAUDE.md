# ARME-tools

Инструменты ARME Engineers для расчетов преднапряженных плит (לוח"דים) в PRET (МКЭ): подготовка нагрузок и сборка PDF-отчетов для заводов. Python 3.11, без тестового фреймворка и CI.

## Состав

Логика живет в движках, оболочки отвечают только за ввод и вывод. Изменение в движке проверять во всех его оболочках (CLI, tkinter, Streamlit).

| Движок | Назначение | Оболочки |
|---|---|---|
| `pret_loads.py` | Текстовый ввод нагрузок и сечений, таблица для PRET (Lsprd, DL/LL/SDL на полосу, ST, Lspr(max), Kspr(max)), CLI | `pret_loads_gui.py`, `pret_loads_app.py` |
| `annotate_loading.py` | Разбор имени PDF расчета, поиск страницы `L o a d i n g`, наложение аннотаций нагрузок (reportlab overlay + pypdf merge) | вызывается из `build_report.py` |
| `build_report.py` | Сборка отчета: титул, легенда, оглавление со ссылками, номера страниц, метаданные PDF, CLI | `build_report_gui.py`, `build_report_app.py` |
| `config.py` | Организация, заводы `FACTORIES`, `detect_factory()` по номеру проекта, `PROJECTS_ROOT` | все |

`logos/` и `fonts/`: логотипы заводов и FreeSans для иврита. `BUILD_INSTRUCTIONS_GUI.md`: сборка .exe через PyInstaller и таблица заводов.

## Команды

```bash
pip install -r requirements.txt          # + Pillow для логотипа в GUI; системные пакеты в packages.txt
python -m py_compile *.py                # синтаксис всех модулей
python annotate_loading.py               # самотесты parse_filename и compute_loads
python pret_loads.py input.txt -o out/   # калькулятор нагрузок из файла
python build_report.py 1382 --floor "+14"  # нужен PROJECTS_ROOT с расчетами; в облаке данных нет
streamlit run pret_loads_app.py          # devcontainer поднимает его на порту 8501
```

Для визуальной проверки PDF в облаке: `pip install pymupdf`, рендер страницы в PNG и просмотр изображения.

## Инженерная часть

- Константы `BAND = 1.20` м, `RHO = 2.50` т/м³, `KSPR = 0.96` продублированы в `pret_loads.py` и `annotate_loading.py`. Менять только вместе и только по явному указанию.
- Формулы: SDL = top · RHO · BAND; DL и LL на полосу = q · BAND; для ST: half = ST/2, DL-ST = DL · half, бетон ST = half · (h + top) · RHO; Lsprd = min(round((ST/2 + BAND) · 100), 150) см; Lspr(max) = 0,4 L; Kspr(max) = 2 / Lspr(max).
- Единицы на входе: DL+LL в кг/м², если значение ≥ 50, иначе т/м²; длины в см, если ≥ 100, иначе м. На выходе т/м и т/м². Только метрическая система.
- Источник коэффициентов в коде не указан. При изменении формул писать в комментарии стандарт и пункт (ת"י, EN); непроверенный пункт помечать «уточнить», номера не придумывать.
- После изменения формул: самотесты зеленые, одна строка таблицы пересчитана отдельно в Python с формулой, словесный вывод сверен с числами.

## Контракты, которые легко сломать

- Имя файла расчета: `nn-h-L+STxx (DL+LL).pdf`, например `01-40-1385+ST25 (350+500).pdf`. Высота может иметь буквенный префикс (`A30`), текст между параметрами и скобками игнорируется. Любое изменение `parse_filename` сопровождать новым случаем в `_test_parse`.
- `detect_factory`: 1000-1999 sela, 2200-2999 ramet, 6900+ denia, `YY-NN` haifa, `YYYY-NN` arad. Новый завод: `FACTORIES` + логотип в `logos/` + `detect_factory` + таблица в `BUILD_INSTRUCTIONS_GUI.md`.
- Иврит в PDF: визуальный порядок через `python-bidi` (`get_display`), шрифт FreeSans, выравнивание вправо. Текстовый слой не доказывает правильность: после правок вывода смотреть отрендеренную страницу.
- PyInstaller: GUI ищет файлы через `sys._MEIPASS`. Новый модуль или папку, нужную в рантайме, добавить в `--add-data` в `BUILD_INSTRUCTIONS_GUI.md`.

## Известные расхождения

Не чинить попутно, только отдельной задачей:

- Версии: код v2.1, `BUILD_INSTRUCTIONS_GUI.md` местами пишет v2.0.
- `build_report_gui.py:92` ссылается в комментарии на `config.get_email()`, которой нет.
- Жесткие Windows-пути: `config.PROJECTS_ROOT`, `pret_loads.DEFAULT_SAVE_DIR`.
- Тема Streamlit лежит в `streamlit/config.toml` и `config.toml` в корне, а Streamlit читает только `.streamlit/config.toml`.
- В докстрингах и строках интерфейса много U+2014.

## Конфиденциальность

Репозиторий публичный. Не коммитить реальные PDF расчетов, названия и адреса проектов клиентов, количества, цены и контакты. Примеры и тесты только на синтетических данных. Ключи и токены брать из переменных окружения.

## Стиль кода

- Повторять существующий: докстринг модуля с шапкой ARME, разделители `# ── ... ──`, необязательные зависимости в `try/except` с флагами `*_OK`, ивритские строки литералами.
- В новом коде, комментариях и строках интерфейса не использовать U+2014 и U+2013. В существующем коде заменять только в строках, которые правишь, без массовой переписки. Проверка добавленных строк:
  `git diff -U0 | grep '^+' | grep -nP "(*UTF)[\x{2012}-\x{2015}\x{2212}]"`
- Не коммитить `__pycache__/`, `build/`, `dist/`, `*.spec`.
- Сообщения коммитов описывают изменение, а не «Add files via upload».

## Агентная работа

- When a step doesn't need my input, keep going. Put status notes in the same message as your next action. Stop and ask only when you can't continue without me, or before anything destructive: deleting data, force-pushing, or changing anything outside this repository.
- «Готово» по умолчанию: `py_compile` проходит, самотесты зеленые, затронутые оболочки импортируют движок без ошибок, при изменении PDF-вывода отрендеренная страница просмотрена.
- Облачное окружение временное: все, что нужно сохранить, коммитить.
