"""Generate data/emails.json: 50 realistic emails, each with gold event details.

Run once: `uv run python data/make_emails.py`. Deterministic (seeded).
Gold fields match the ExtractEvent signature: event_name, date, start, duration_minutes.
"""

import datetime as dt
import json
import random
from pathlib import Path

random.seed(329)

# (event_name, body). 50 distinct scenarios. Bodies use {date}, {time}, {dur} placeholders.
SCENARIOS = [
    ("dental cleaning", "Hi Alex,\n\nThis is a reminder that your dental cleaning is scheduled for {date} at {time}.{dur} Please arrive ten minutes early to update your insurance information.\n\nThanks,\nFront Desk, Palo Alto Dental"),
    ("Q3 budget review", "Team,\n\nI've moved the Q3 budget review to {date} at {time}.{dur} Please have your department numbers in the shared sheet beforehand.\n\nBest,\nPriya"),
    ("parent-teacher conference", "Dear families,\n\nYour parent-teacher conference with Ms. Alvarez is confirmed for {date} at {time}.{dur} We will meet in room 14.\n\nWarmly,\nLincoln Elementary"),
    ("phone interview", "Hello,\n\nThank you for applying to the Data Analyst role. We'd like to schedule a phone interview on {date} at {time}.{dur} A calendar invite will follow.\n\nRegards,\nTalent Team"),
    ("oil change", "Your appointment is confirmed!\n\nService: oil change\nWhen: {date} at {time}{dur}\nWhere: Midtown Auto, 410 El Camino Real\n\nReply STOP to cancel."),
    ("book club", "Hey everyone,\n\nBook club is on {date} at {time} at my place.{dur} We're discussing the second half of the novel, so finish it if you can!\n\nSee you there,\nJordan"),
    ("1:1 with Dana", "Hi,\n\nCan we do our 1:1 with Dana on {date} at {time}?{dur} I want to go over the quarterly goals.\n\nThanks!"),
    ("product demo", "Hi all,\n\nThe product demo for the Acme account is set for {date} at {time}.{dur} Engineering, please make sure the staging environment is stable.\n\nCheers,\nMarcus"),
    ("yoga class", "Namaste,\n\nYou're booked for yoga class on {date} at {time}.{dur} Bring your own mat or rent one at the studio for $2.\n\nStudio Flow"),
    ("flu shot", "Hello,\n\nYour flu shot appointment is confirmed for {date} at {time}.{dur} No fasting required. Wear a short-sleeved shirt.\n\nCVS Pharmacy"),
    ("thesis defense", "Dear committee members,\n\nThe thesis defense for Wei Zhang will take place on {date} at {time} in Gates 104.{dur} The dissertation is attached.\n\nSincerely,\nGraduate Program Office"),
    ("onboarding session", "Welcome aboard!\n\nYour onboarding session is scheduled for {date} at {time}.{dur} Please bring two forms of ID for the I-9 verification.\n\nPeople Ops"),
    ("design review", "Folks,\n\nDesign review for the checkout redesign: {date}, {time}.{dur} Figma link is in the channel. Come with opinions.\n\n- Sam"),
    ("vet appointment", "Hi,\n\nBiscuit's vet appointment is booked for {date} at {time}.{dur} Please bring any records from the previous clinic.\n\nSunnyvale Animal Hospital"),
    ("apartment viewing", "Hello,\n\nConfirming your apartment viewing at 220 Hamilton Ave on {date} at {time}.{dur} Text me if you're running late.\n\nBest,\nRenee (Leasing)"),
    ("piano lesson", "Hi Taylor,\n\nJust confirming next piano lesson: {date} at {time}.{dur} Please practice the Chopin for the first half.\n\nThanks,\nMr. Okafor"),
    ("sprint retrospective", "Hi team,\n\nSprint retrospective is on {date} at {time}.{dur} Add your notes to the retro board before then.\n\nThanks,\nScrum Master"),
    ("investor pitch", "Hi,\n\nWe've got the investor pitch with Sequoia on {date} at {time}.{dur} Please send me the latest deck by tomorrow EOD.\n\nThanks,\nLena"),
    ("haircut", "Appointment reminder: haircut with Jesse on {date} at {time}.{dur} Reply C to confirm or R to reschedule.\n\nThe Cut Shop"),
    ("volunteer shift", "Thanks for signing up!\n\nYour volunteer shift at the food bank is {date} at {time}.{dur} Closed-toe shoes required.\n\nSecond Harvest"),
    ("board meeting", "Directors,\n\nThe board meeting is scheduled for {date} at {time}.{dur} Materials will be circulated 48 hours in advance.\n\nCorporate Secretary"),
    ("physical therapy", "Hello,\n\nYour physical therapy session is confirmed for {date} at {time}.{dur} Please wear comfortable clothing.\n\nBay Area PT"),
    ("campus tour", "Hi,\n\nYou're registered for the campus tour on {date} at {time}.{dur} We meet at the visitor center.\n\nAdmissions Office"),
    ("tax appointment", "Hi,\n\nYour tax appointment with Carol is set for {date} at {time}.{dur} Bring your W-2s and any 1099s.\n\nGreenleaf Accounting"),
    ("rehearsal", "Hi cast,\n\nRehearsal is {date} at {time}.{dur} We'll run Act II. Off-book, please!\n\nDirector"),
    ("car inspection", "Hi,\n\nYour vehicle inspection is booked for {date} at {time}.{dur} Please bring your registration and proof of insurance.\n\nPeninsula Auto Care"),
    ("eye exam", "Hello,\n\nThis confirms your eye exam with Dr. Nakamura on {date} at {time}.{dur} Please bring your current glasses or contacts.\n\nBay Vision Center"),
    ("grant proposal review", "Hi all,\n\nThe grant proposal review for the NSF submission is on {date} at {time}.{dur} Please read the draft budget beforehand.\n\nThanks,\nRosa"),
    ("guitar lesson", "Hey Sam,\n\nNext guitar lesson is {date} at {time}.{dur} Work on the F barre chord before then!\n\nDave"),
    ("plumber visit", "Hello,\n\nOur plumber is scheduled to visit on {date} at {time} to look at the kitchen leak.{dur} Someone over 18 needs to be home.\n\nRapid Rooter"),
    ("customer call", "Hi team,\n\nCustomer call with Northwind Logistics is set for {date} at {time}.{dur} Dial-in details are in the calendar invite.\n\nBest,\nIngrid"),
    ("swim lesson", "Hi,\n\nMaya's swim lesson is confirmed for {date} at {time}.{dur} Please arrive changed and ready.\n\nAquatics Center"),
    ("mortgage consultation", "Hello,\n\nYour mortgage consultation with Patrick is booked for {date} at {time}.{dur} Please have your last two pay stubs handy.\n\nFirst Street Lending"),
    ("code review", "Hi,\n\nCan we do the code review for the payments refactor on {date} at {time}?{dur} The PR is #482.\n\nThanks,\nNoor"),
    ("passport appointment", "Hello,\n\nYour passport appointment is scheduled for {date} at {time}.{dur} Bring your completed DS-11 and two photos.\n\nU.S. Postal Service"),
    ("choir practice", "Hi singers,\n\nChoir practice is {date} at {time} in the chapel.{dur} We'll be working on the Rutter.\n\nEleanor"),
    ("quarterly planning", "Team,\n\nQuarterly planning is on {date} at {time}.{dur} Come with your top three priorities for next quarter.\n\nThanks,\nDesmond"),
    ("allergy shot", "Hello,\n\nYour allergy shot appointment is confirmed for {date} at {time}.{dur} Please wait 30 minutes after the injection as usual.\n\nValley Allergy Clinic"),
    ("tutoring session", "Hi Priyanka,\n\nTutoring session for AP Calculus is set for {date} at {time}.{dur} Bring the problem set from chapter 7.\n\nMr. Hale"),
    ("movers arriving", "Hello,\n\nYour movers are scheduled to arrive on {date} at {time}.{dur} Please have everything boxed and labeled.\n\nGolden Gate Moving"),
    ("hiring committee", "Hi,\n\nThe hiring committee meets on {date} at {time} to discuss the finalists.{dur} Scorecards are due the night before.\n\nThanks,\nAmara"),
    ("pottery class", "Hi,\n\nYou're signed up for pottery class on {date} at {time}.{dur} Wear clothes you don't mind getting clay on.\n\nClay Studio"),
    ("furnace maintenance", "Hello,\n\nAnnual furnace maintenance is scheduled for {date} at {time}.{dur} Please clear access to the utility closet.\n\nComfort Heating"),
    ("thesis committee meeting", "Dear Prof. Lindqvist,\n\nMy thesis committee meeting is scheduled for {date} at {time} in Huang 018.{dur} I'll circulate slides two days before.\n\nBest,\nTomas"),
    ("soccer practice", "Hi parents,\n\nSoccer practice is {date} at {time} on the north field.{dur} Shin guards required.\n\nCoach Reyes"),
    ("bank appointment", "Hello,\n\nYour appointment to open a business account is booked for {date} at {time}.{dur} Please bring your EIN letter.\n\nWells Fargo"),
    ("press briefing", "Hi all,\n\nThe press briefing for the product launch is on {date} at {time}.{dur} Please be in the lobby ten minutes early.\n\nComms Team"),
    ("massage", "Hi,\n\nYour massage with Lena is confirmed for {date} at {time}.{dur} Please arrive a few minutes early to fill out the intake form.\n\nSerenity Spa"),
    ("study group", "Hey,\n\nStudy group for the CS329Z midterm is {date} at {time} in the Green Library.{dur} Bring your notes on optimizers.\n\nJules"),
    ("home inspection", "Hello,\n\nThe home inspection for 88 Cowper St is scheduled for {date} at {time}.{dur} The inspector will need access to the attic.\n\nRedwood Realty"),
]

DATE_STYLES = [
    lambda d: d.strftime("%A, %B %-d, %Y"),           # Thursday, October 15, 2026
    lambda d: d.strftime("%b %-d, %Y"),               # Oct 15, 2026
    lambda d: d.strftime("%-m/%-d/%Y"),               # 10/15/2026
    lambda d: d.strftime("%B %-d") + {1: "st", 2: "nd", 3: "rd", 21: "st", 22: "nd", 23: "rd", 31: "st"}.get(d.day, "th") + d.strftime(", %Y"),  # October 15th, 2026
    lambda d: d.strftime("%-d %B %Y"),                # 15 October 2026
    lambda d: d.strftime("%a %-m/%-d/%Y"),            # Thu 10/15/2026
]

def time_text(t: dt.time) -> str:
    h12 = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    if t == dt.time(12, 0) and random.random() < 0.5:
        return "noon"
    style = random.choice(["colon", "colon_lower", "dots", "24h", "bare"])
    if style == "24h":
        return t.strftime("%H:%M")
    if t.minute == 0 and style == "bare":
        return f"{h12} {ampm}"
    if style == "dots":
        return f"{h12}:{t.minute:02d} {ampm.lower()[0]}.m."
    if style == "colon_lower":
        return f"{h12}:{t.minute:02d}{ampm.lower()}"
    return f"{h12}:{t.minute:02d} {ampm}"

DURATIONS = [  # (minutes or None, phrase)
    (30, " It should take about 30 minutes."),
    (30, " Plan for half an hour."),
    (45, " Please allow 45 minutes."),
    (60, " Block off an hour."),
    (60, " It will run for one hour."),
    (90, " Expect it to last about 90 minutes."),
    (120, " It's a two-hour session."),
    (15, " It's a quick 15-minute check-in."),
    (None, ""),
    (None, ""),
    (None, ""),
]

TIMES = [dt.time(h, m) for h in range(8, 19) for m in (0, 15, 30, 45)]

rows = []
assert len({name for name, _ in SCENARIOS}) == 50
scenarios = list(SCENARIOS)
random.shuffle(scenarios)
for name, body in scenarios:
    d = dt.date(2026, 10, 5) + dt.timedelta(days=random.randint(0, 80))
    while d.weekday() >= 5:  # keep appointments on weekdays
        d += dt.timedelta(days=1)
    t = random.choice(TIMES)
    minutes, phrase = random.choice(DURATIONS)
    email = body.format(date=random.choice(DATE_STYLES)(d), time=time_text(t), dur=phrase)
    rows.append({"email": email, "event_name": name, "date": d.isoformat(),
                 "start": t.strftime("%H:%M"), "duration_minutes": minutes})

out = Path(__file__).with_name("emails.json")
out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), "utf-8")
print(f"wrote {len(rows)} emails to {out}")
