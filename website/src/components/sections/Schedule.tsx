import { Reveal } from "@/components/ui/Reveal";
import { schedule, providers, providersNote, week } from "@/content/site";

/**
 * Schedule → fueling. Shows the INPUT side only: the week as imported.
 * The fueling day it produces is demonstrated by the questions explorer above,
 * so repeating a full timeline here would be the same content twice.
 */
export function Schedule() {
  return (
    <section id="schedule" className="section surface-dark" aria-labelledby="s-h">
      <div className="container split-2">
        <Reveal>
          <span className="eyebrow">{schedule.eyebrow}</span>
          <h2 id="s-h" className="h2">{schedule.h2}</h2>
          <p className="body muted-txt">{schedule.body}</p>
          <p className="small muted-txt" style={{ marginTop: "var(--s4)", fontWeight: 700, color: "var(--on-dark)" }}>
            {schedule.chipsLabel}
          </p>
          <ul className="chip-grid chip-grid--2" style={{ marginTop: "var(--s3)" }} aria-label="Club calendars you can import">
            {providers.map((p) => <li key={p} className="chip chip--i">{p}</li>)}
          </ul>
          <p className="small muted-txt" style={{ marginTop: "var(--s3)" }}>{providersNote}</p>
        </Reveal>

        <Reveal className="card--dark wk" i={1}>
          <p className="wk__h">{schedule.weekLabel}</p>
          <ol className="wk__rows">
            {week.map((e) => (
              <li key={e.day} className="wk__row">
                <span className="wk__day">{e.day}</span>
                <span className={`wk__dot${e.game ? " wk__dot--game" : ""}`} aria-hidden />
                <span className="wk__kind">{e.kind}</span>
                <span className="wk__time">{e.time}</span>
                <span className="wk__win">{e.windows} windows</span>
              </li>
            ))}
          </ol>
          <p className="wk__note">{schedule.syncNote}</p>
        </Reveal>
      </div>
    </section>
  );
}
