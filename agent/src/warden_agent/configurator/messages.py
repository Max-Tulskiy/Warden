"""Everything the connection window and its command line say, in Russian.

One catalog, so that a test can check that nothing shown to an administrator is
in another language (constitution principle 9). A text with `{name}` takes that
value through `str.format`. Qt's own standard buttons are never used, since
their labels depend on translation files that are not shipped.
"""

WINDOW_TITLE = "Warden Agent — настройка"

# What the window says a failure was, by the code the agent stores for it.
ERROR_UNREACHABLE = "сервер недоступен"
ERROR_CERTIFICATE_NOT_TRUSTED = "сертификат сервера не доверен"
ERROR_CREDENTIAL_REFUSED = "сервер отклонил ключ или токен станции"
ERROR_SERVER_ERROR = "ошибка на стороне сервера"
ERROR_OTHER = "неопознанная ошибка"

# Why an agent that is waiting is waiting.
WAITING_NOT_CONFIGURED = "ожидает настройки: станция не подключена к серверу"
WAITING_SERVER_CHANGED = (
    "ожидает: ключ станции выдан другим сервером, зарегистрируйте её заново"
)
WAITING_CA_UNREADABLE = "ожидает: файл доверенного сертификата не читается"

# The result of checking an address.
CHECK_UNREACHABLE = "Сервер {server} недоступен. Проверьте адрес и сеть."
CHECK_UNTRUSTED = "Сервер отвечает, но его сертификат не доверен."
CHECK_TRUSTED = "Сервер доступен, его сертификат доверен."
CHECK_UNEXPECTED = "Адрес отвечает неожиданно (код {code}). Это точно сервер Warden?"

# The result of connecting.
CONNECTED = "Станция подключена к серверу {server}."
ALREADY_CONNECTED = "Станция уже подключена к серверу {server}."
ENROLLMENT_REFUSED = "Сервер отклонил токен регистрации: {detail}"
SERVER_FAILED = "Сервер ответил ошибкой (код {code}). Ничего не сохранено."
NO_AUTHORITY = (
    "Сервер не предлагает собственного центра сертификации, поэтому его "
    "сертификат должен быть доверенным в системе."
)
FINGERPRINT_MISMATCH = (
    "Отпечатки не совпадают: ожидался {expected}, сервер предлагает {actual}. "
    "Ничего не сохранено."
)
TRUST_NOT_GIVEN = "Сертификат сервера не доверен, станция не подключена."
NEEDS_REPLACE = (
    "Станция уже зарегистрирована на сервере {current}. Чтобы подключить её к "
    "другому серверу, подтвердите замену."
)
NOT_CONNECTED = "Станцию не удалось подключить. Ничего не сохранено."
CONFIG_TOO_COMPLEX = (
    "В файле настроек есть таблицы или списки, которые нельзя перезаписать без "
    "потерь. Отредактируйте файл вручную."
)

# The rest of the reasons a connection can end without connecting.
REFUSED_INVALID_ADDRESS = (
    "Адрес сервера выглядит неправильно. Укажите его целиком, например "
    "https://warden.example.internal."
)
REFUSED_INVALID_FINGERPRINT = (
    "Указанный отпечаток не похож на SHA-256: нужны 64 шестнадцатеричные цифры."
)
REFUSED_BLANK_ENROLLMENT = (
    "Введите токен регистрации: его выпускает администратор в панели, на "
    "экране «Станции»."
)
REFUSED_AUTHORITY_INVALID = "Сервер прислал не сертификат, подключиться нельзя."
REFUSED_NOT_VERIFIED = (
    "Сертификат сервера не удалось проверить даже с предложенным центром сертификации."
)
REFUSED_WRITE_FAILED = (
    "Не удалось сохранить настройки (ошибка записи). Станция осталась как была."
)
REFUSED_NOT_ENROLLED = (
    "Станция ещё не зарегистрирована, обновлять доверие пока не для чего."
)

# What the command line prints when a certificate is not trusted yet.
TRUST_OFFERED = (
    "Сертификат сервера не доверен, но сервер предлагает собственный центр "
    "сертификации.\n"
    "Кем выдан: {subject}\n"
    "Отпечаток SHA-256: {fingerprint}\n"
    "Сверьте отпечаток с показанным в панели (раздел «Станции») и повторите "
    "команду с параметром --ca-sha256."
)

# The state block of the window.
LABEL_SERVICE = "Служба"
LABEL_AGENT = "Агент"
LABEL_STATION = "Станция"
LABEL_LAST_CONTACT = "Последний обмен"
LABEL_LAST_ERROR = "Последняя ошибка"
SERVICE_RUNNING = "работает"
SERVICE_STOPPED = "остановлена"
SERVICE_NOT_INSTALLED = "не установлена"
SERVICE_NOT_APPLICABLE = "не применимо"
AGENT_RUNNING = "работает"
AGENT_UNKNOWN = "нет данных"
STATION_ENROLLED = "зарегистрирована на {server}"
STATION_NOT_ENROLLED = "не зарегистрирована"
LAST_CONTACT_NEVER = "ещё не было"
LAST_ERROR_NONE = "нет"

# What the window says while and after it works.
BANNER_NOT_ADMIN = (
    "Нужны права администратора: изменить подключение можно только от его имени."
)
TRUST_UPDATED = "Доверие к серверу {server} обновлено."
UNEXPECTED_FAILURE = (
    "Не удалось выполнить действие. Подробности записаны в журнал настройки."
)
