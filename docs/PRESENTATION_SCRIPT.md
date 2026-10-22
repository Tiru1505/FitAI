# FitAI — second review: line-by-line speaking script

Total ≈ 11 minutes (8 slides ≈ 7 min, live demo ≈ 4 min). Lines in plain text are what you say.
**Bold text in brackets** is a stage direction, not spoken.

---

## Slide 1 — Title  ·  45 seconds

**[Stand still. Do not read the slide title aloud — they can read.]**

Good morning. This is FitAI, an adaptive fitness assistant that uses deep learning to analyse
exercise from an ordinary webcam.

The idea in one sentence: you do your workout in front of your laptop, the system counts your
repetitions, comments on your technique, and adjusts next week's plan based on how you actually
performed.

**[Point at the three numbers.]**

Since the zeroth review we have trained and evaluated four models, processed 310 exercise sets from
a public dataset, and the application itself is running with 68 automated tests passing.

I will cover what we built, show it running, give you our preliminary numbers, and be honest about
what is not finished.

---

## Slide 2 — Recap: problem and proposed system  ·  60 seconds

A quick recap of the problem.

People who train at home get no feedback on their technique. Bad form is how injuries happen, and
nobody is watching. Second, generic plans ignore what you actually managed last week — they do not
adapt.

So our objective is two things: recognise the exercise and judge it live, and then adapt the next
workout from what was measured, in a way the user can understand.

**[Move hand down the numbered list on the right.]**

The proposed system has five stages. The user sets a profile and goals. A rule-based generator
writes an explainable plan. During a session, pose estimation runs in the browser. The server
analyses the movement with a BiLSTM and a joint-angle state machine. Finally an adaptive coach
updates the plan.

**[Point at the amber box. Say this clearly — do not rush it.]**

One deviation from what we proposed. Form-error classification is still rule-based, not a neural
network. The reason is data: no public dataset labels incorrect form. Every dataset we found records
people exercising correctly. I will come back to this.

---

## Slide 3 — Implementation overview  ·  75 seconds

This is what is actually built, against the full proposed pipeline.

**[Top row, left to right.]**

The top row runs in the browser. The webcam feeds Google's MediaPipe pose model, which finds 33
body points per frame. Only those numbers go over the WebSocket.

I want to stress that: the video never leaves the user's machine. We send coordinates, not images.
That is a privacy decision we made deliberately and it is why the app can honestly say your video is
never uploaded.

**[Middle row.]**

The server normalises the landmarks — centred on the hips and divided by body size, so where you
stand and how tall you are stop mattering. Then the repetition counter, the form rules, and the
BiLSTM that names the exercise.

**[Bottom row.]**

The bottom row is the product: authentication, the plan generator, the adaptive coach, progress
tracking, and nutrition guidance from a USDA food table.

**[Point to the legend.]**

Dark teal is built and tested. Green is trained but still needs our own data. Grey is pending — the
form classifier, our own recorded dataset, and deployment.

---

## Slide 4 — Models run and steps completed  ·  60 seconds

Four models, all trained on the same data and the same split.

First, a deliberate baseline: logistic regression on simple summary statistics of each window —
mean, standard deviation, minimum and maximum. It throws away all time information. We included it
to find out how much the sequence modelling is really buying us.

Then the BiLSTM, which is our primary model, a GRU for comparison, and a fourth run of the BiLSTM
with augmentation and stronger regularisation.

All four see the same input: a two-second window, 60 frames, 99 numbers per frame.

**[Right-hand card.]**

On the novel pipeline we are nine steps of twelve. Dataset conversion, the feature pipeline, the
repetition counter and form rules, four models with evaluation, and the full application are done.
Outstanding are the form classifier, our own recorded dataset, and deployment — and all three depend
on data we need to record ourselves.

---

## Slide 5 — Implementation evidence  ·  45 seconds, then the live demo

Evidence that this runs rather than exists on paper.

**[Left card.]** That is the model definition — two bidirectional LSTM layers, dropout, and a
five-way softmax.

**[Right card.]** That is the tail of the execution log from the full run, showing all four models
with their scores and inference times.

**[Bottom strip.]** And that is the command that reproduces it.

**[Now switch to the terminal and run the short version. Talk while it runs.]**

Let me run the pipeline now. I am using three epochs so it finishes while we talk — the numbers I
report are from the full thirty-epoch run.

**[While it runs, narrate:]** It is building the windows and splitting by participant, then training
the baseline, then the BiLSTM, then evaluating on held-out people.

**[When it finishes, switch to the app.]**

And this is the application. **[Start a session, enable the camera, do 3–5 squats.]** The repetition
count is coming from the server, not the browser. The feedback line is the rule-based form check.

**[Finish the session, rate difficulty.]** And here the plan updates itself — with a written reason
for the change, which was a design requirement: no silent adjustments.

---

## Slide 6 — Preliminary results  ·  90 seconds

Our results. The test set is five workouts whose subjects never appear in training — 2,472 windows.

**[Point at the chart.]**

The GRU reaches 0.999 macro F1 and the augmented BiLSTM reaches 1.000. The plain BiLSTM is 0.988.

**[Slow down here. This is the paragraph that earns credibility.]**

But look at the first bar. Logistic regression — no sequence modelling at all — reaches 0.9915. So
on this dataset, our deep models are not proven necessary, and I would rather say that than imply
otherwise.

The explanation is that these five exercises separate by posture alone. Lying down versus standing.
Arms overhead versus arms at your sides. All filmed in a studio with one fixed camera. That is an
easy problem.

Where a recurrent model should genuinely earn its place is form-error classification, because the
difference between a good squat and a bad one is temporal — it is in how the movement develops. That
is exactly the part we cannot train yet.

**[Right card.]**

The repetition counter is geometry, not learning. Against ground-truth counts it is perfect on
biceps curls and near-perfect on lunges, but squats and push-ups are poor. I will explain why on the
next slide.

---

## Slide 7 — Challenges and deviations  ·  90 seconds

Four challenges. The first one is the one I would most like you to notice.

**[Card 1.]**

Our first set of results looked good, and they were wrong. MM-Fit has 21 workouts, but they come
from only about ten people — some people recorded several sessions. So splitting the data by workout
number does not guarantee that test subjects are unseen.

We caught it because the cross-validation scores came out implausibly perfect. We discarded those
results and re-ran everything on the split the dataset authors designed for unseen subjects. The
discarded numbers are still in our report, with the reason.

**[Card 2.]**

Second, as I mentioned: no public dataset labels bad form, so the classifier waits on our own
recordings.

**[Card 3.]**

Third, 17 of 64 squat sets counted zero repetitions. The cause is geometric: MM-Fit films head-on,
and from the front the knee angle is foreshortened, so it never crosses our depth threshold. The
counter never over-counts squats, which is consistent with a threshold that is too strict for that
camera angle rather than random error. The app now tells users to stand side-on.

**[Card 4.]**

Fourth, a practical one. Inference initially took about 500 milliseconds per window, far too slow
for live use. Compiling the model into a fixed-signature graph brought it to about 7 milliseconds.

**[Amber strip.]**

And one limitation we carry forward: the model learned from studio poses produced by a different
tracker than the browser uses, so live accuracy will be lower than the table suggests.

---

## Slide 8 — Updated timeline  ·  45 seconds

Four weeks to the final review.

Week one is the one that unblocks everything else: record our own dataset. Eight to ten volunteers,
five exercises, correct form and deliberate errors, from the front and the side. The recording tool
is already built into the app and stores only landmarks, never video.

Week two, train the form classifier on those error labels and compare it against our geometric rules.

Week three, measure live performance on a real webcam — latency, dropped frames, and repetition
accuracy with real users.

Week four, a small usability study, deployment, and the final report.

So at the final review you should expect a form classifier trained on our own labelled error data,
webcam-measured performance, a deployed application, and the completed evaluation report.

Thank you — I am happy to take questions.

---

## If you have 30 seconds to close instead

What we have shown today is a complete working pipeline with four models evaluated honestly on
unseen people, and an application that runs end to end. What we have not shown is the form
classifier, because the data for it does not exist publicly and we will record it ourselves. Thank
you.
