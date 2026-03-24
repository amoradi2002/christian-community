import json
from flask import Blueprint, render_template, request, flash, redirect, url_for
from bot.learning.youtube import process_video, get_lesson_history

youtube_bp = Blueprint("youtube", __name__)


@youtube_bp.route("/learn", methods=["GET", "POST"])
def learn_page():
    result = None

    if request.method == "POST":
        url = request.form.get("video_url", "").strip()
        if not url:
            flash("Please enter a YouTube URL.", "error")
            return redirect(url_for("youtube.learn_page"))

        result = process_video(url)

        if result["status"] == "success":
            flash(
                f"Extracted {result['strategies_found']} strategy(ies) from \"{result['title']}\"! "
                f"{result['strategies_saved']} new strategy(ies) saved (disabled by default — review and enable in Strategies).",
                "success",
            )
        elif result["status"] == "already_processed":
            flash(result["message"], "success")
        elif result["status"] == "no_transcript":
            flash(result["message"], "error")
        else:
            flash(result.get("message", "Something went wrong."), "error")

    lessons = get_lesson_history(limit=30)
    return render_template("learn.html", lessons=lessons, result=result)
