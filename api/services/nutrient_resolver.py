def queue_nutrient_resolution(log_id: int, conn) -> None:
    """
    Seam for the future photo→nutrient AI.
    For now: mark the log's nutrient_status = 'pending' and return.
    When the real engine ships it will compute macros, write them to
    window_logs server-side, set status='resolved', and recompute readiness.
    The athlete client never receives the macro numbers — only nutrient_status.
    """
    conn.execute(
        "UPDATE window_logs SET nutrient_status = 'pending' WHERE id = %s",
        (log_id,),
    )
    conn.commit()
