"""Generate a clearly synthetic PDF for end-to-end testing, never a research claim."""
from pathlib import Path
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
root=Path(__file__).resolve().parents[1]
out=root/'data/demo-paper.pdf'
styles=getSampleStyleSheet()
sections=[('A Tiny Queue Scheduler: A Synthetic Review Test',[
('Abstract','This intentionally incomplete synthetic paper tests a local peer-review pipeline. It proposes a two-queue scheduler for interactive and batch requests, using an exponentially weighted latency estimate. All results below are illustrative invented numbers, not empirical evidence. The paper is not intended for publication.'),
('1. Motivation','An interactive request can wait behind a long batch request on a serial server. We aim to reduce interactive tail latency without starving batch work. The setting is one server with non-preemptive jobs and known job classes. We do not model distributed execution, accelerators, admission control, or failures.'),
('2. Method','Maintain FIFO queues I and B. After serving at most K interactive requests, serve one batch request if B is not empty. If I is empty, serve B immediately. K=4 is fixed throughout. This is a weighted round-robin policy, not a novel scheduling primitive. Arrival timestamps are measured at admission. An exponentially weighted latency estimate L is updated as L = 0.8 L + 0.2 observed_latency but is only logged and does not affect the scheduling decision.')]),
('Analysis and illustrative evaluation',[
('3. Analysis','With a permanently nonempty interactive queue, a waiting batch request receives service after at most K interactive completions plus the batch work ahead of it. This is a bound on job counts, not elapsed time. Without a bound on service times, no constant wall-clock waiting bound follows. We assume stable load but do not prove stochastic stability or mean-delay guarantees.'),
('4. Evaluation design','We describe, but did not execute, a single-server simulation with 10000 requests: 80 percent interactive and 20 percent batch. Proposed service durations are 1 ms and 20 ms. The baseline is FIFO. We would report p50 and p99 interactive latency, batch waiting time, total throughput and confidence intervals over five seeds. These measurements have not been collected.'),
('4.1 Illustrative table','For exercising PDF text extraction only, the following numbers are fabricated: FIFO interactive p99 = 200 ms; K=4 scheduler p99 = 80 ms; throughput = 180 requests/s for both. These numbers cannot support an improvement claim. There are no traces, error bars, scripts, hardware measurements, ablations, or comparisons to shortest-job-first or deficit round-robin.')]),
('Limitations and conclusion',[
('5. Limitations','The proposal assumes an accurate class label and neglects scheduler overhead. Batch jobs may still block interactive requests during non-preemptive service. Different arrival rates or heavy-tailed service times could reverse the illustrative comparison. K was not tuned or ablated. The latency estimator is unused. The work lacks a novelty argument and related-work review.'),
('6. Conclusion','This document exists only as a local pipeline test. Reviewers should identify its lack of empirical evidence, limited novelty and incomplete analysis, and should not treat invented values as real results. A viable paper would require an implemented system, defensible baselines, reproducible workloads, uncertainty estimates and evidence of a new contribution.')])]
flow=[]
for idx,(title,parts) in enumerate(sections):
 if idx: flow.append(PageBreak())
 flow.append(Paragraph(title,styles['Title']))
 for heading,body in parts:
  flow.extend([Spacer(1,14),Paragraph(heading,styles['Heading2']),Paragraph(body,styles['BodyText'])])
SimpleDocTemplate(str(out)).build(flow)
print(out)
