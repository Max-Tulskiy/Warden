"""Schemas for the operating policy shown and edited in the panel's settings."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

#: The longest request window there can ever be: the constitution's four hours
#: (principle 3). It is a constant, never a setting: no configuration and no
#: saved policy can raise it, only lower the limit beneath it.
WINDOW_HOURS_CEILING = 4

#: What an administrator may set, as (lowest, highest). The window's highest is
#: the ceiling above; the others bound how long access credentials can last.
WINDOW_HOURS_BOUNDS = (1, WINDOW_HOURS_CEILING)
TOKEN_TTL_HOURS_BOUNDS = (1, 168)
SESSION_MINUTES_BOUNDS = (5, 1440)

# Strict integers: `2.5`, `"2"` and `true` are refused rather than coerced.
WindowHours = Annotated[
    int, Field(strict=True, ge=WINDOW_HOURS_BOUNDS[0], le=WINDOW_HOURS_BOUNDS[1])
]
TokenTtlHours = Annotated[
    int, Field(strict=True, ge=TOKEN_TTL_HOURS_BOUNDS[0], le=TOKEN_TTL_HOURS_BOUNDS[1])
]
SessionMinutes = Annotated[
    int, Field(strict=True, ge=SESSION_MINUTES_BOUNDS[0], le=SESSION_MINUTES_BOUNDS[1])
]


class PolicyValues(BaseModel):
    """The three values an administrator can change, whatever their source."""

    max_request_window_hours: int
    enrollment_token_ttl_hours: int
    session_lifetime_minutes: int


class PolicyUpdateIn(BaseModel):
    """The body of `PUT /api/v1/policy`: all three values, each within its bounds.

    Nothing else is accepted, and each value must be a whole number.
    """

    model_config = ConfigDict(extra="forbid")

    max_request_window_hours: WindowHours
    enrollment_token_ttl_hours: TokenTtlHours
    session_lifetime_minutes: SessionMinutes


class Bounds(BaseModel):
    """The lowest and highest value an editable setting may take."""

    min: int
    max: int


class PolicyBounds(BaseModel):
    """The range of each editable value, so the panel never has to copy them."""

    max_request_window_hours: Bounds
    enrollment_token_ttl_hours: Bounds
    session_lifetime_minutes: Bounds


class PolicyOut(BaseModel):
    """The operating limits in force, and what an administrator may do with them.

    The three editable values are the ones in force now, whether they came from
    a saved policy (`overridden`) or from the server's configuration. `defaults`
    is what the configuration gives them, which a reset returns to, and `bounds`
    is the range each may take. The other four limits stay in the code.

    An explicit allow-list: every field is named here on purpose, so a secret
    or connection string in `Settings` can never reach the response by being
    added there.
    """

    max_request_window_hours: int
    enrollment_token_ttl_hours: int
    session_lifetime_minutes: int
    min_password_length: int
    max_report_events: int
    max_inventory_entries: int
    max_page_size: int
    overridden: bool
    defaults: PolicyValues
    bounds: PolicyBounds
