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
