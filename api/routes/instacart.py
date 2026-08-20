"""Instacart shopping-list handoff.

POST /api/instacart/shopping-list — accept a grocery list, create an
Instacart-hosted shopping list page via the Developer Platform API, and return
the URL for the client to open. We never touch an existing Instacart cart: the
user reviews product matches, picks a store, and checks out on Instacart's own
page. See docs/instacart-integration.md for the full write-up.

Sibling to instacart_feedback.py (POST /api/instacart/feedback) under the same
/api/instacart prefix — that route already captured post-handoff feedback
before this endpoint existed.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from api.database import get_conn
from api.services import instacart_client
from api.services.instacart_shopping_list import (
    ShoppingListCreateRequest,
    create_shopping_list,
)
from api.services.session_auth import require_session, assert_owns_athlete

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/shopping-list", status_code=201)
def create_instacart_shopping_list(payload: ShoppingListCreateRequest, identity=Depends(require_session)):
    if not instacart_client.instacart_shopping_list_enabled():
        raise HTTPException(404, "Instacart shopping list handoff is not currently available.")

    conn = get_conn()
    try:
        assert_owns_athlete(identity, payload.athlete_id, conn)
        if not conn.execute("SELECT id FROM athletes WHERE id = %s", (payload.athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
    finally:
        conn.close()

    try:
        result = create_shopping_list(payload)
    except instacart_client.InstacartConfigError:
        logger.exception("Instacart not configured")
        raise HTTPException(500, "Instacart integration is not configured.")
    except instacart_client.InstacartAuthError:
        logger.error("Instacart authentication failed for athlete_id=%s", payload.athlete_id)
        raise HTTPException(502, "Could not create the Instacart shopping list right now.")
    except instacart_client.InstacartValidationError as exc:
        logger.warning("Instacart rejected shopping list request: %s", exc.error_code)
        raise HTTPException(400, "One or more items could not be processed by Instacart.")
    except instacart_client.InstacartRateLimitError:
        raise HTTPException(429, "Instacart is temporarily busy. Please try again shortly.")
    except instacart_client.InstacartNetworkError:
        logger.exception("Network error calling Instacart")
        raise HTTPException(502, "Could not reach Instacart right now.")
    except instacart_client.InstacartUnavailableError:
        logger.exception("Instacart unavailable or returned an unexpected response")
        raise HTTPException(502, "Instacart is temporarily unavailable.")
    except ValidationError as exc:
        # Defensive: our own mapping produced something Instacart's schema
        # didn't expect. Should not happen if instacart_shopping_list.py's
        # validators are correct, but never leak internal details either way.
        logger.exception("Unexpected request-mapping error: %s", exc)
        raise HTTPException(500, "Could not create the Instacart shopping list.")

    return result.model_dump()
