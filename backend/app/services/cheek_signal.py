"""Engineering signal index. No clinical hydration, dryness or AU conversion."""
import math
from statistics import median
POLICY = 'cheek-cap-index-v1'

def capacitance_change(baseline, count):
    return (((baseline + 170) / (count + 170)) ** 2 - 1) * 100

def detection_threshold(baseline, counts):
    values=[(baseline-n)*100/baseline for n in counts]
    mean=sum(values)/len(values)
    sd=math.sqrt(sum((x-mean)**2 for x in values)/len(values))
    return max(200/baseline, abs(mean)+6*sd+100/baseline)

def response_precision(baseline, counts):
    m=median(counts)
    def response(b,c):return 100*(1-((c+170)/(b+170))**2)
    center=response(baseline,m)
    lower=response(baseline-0.5,m+0.5)
    upper=response(baseline+0.5,m-0.5)
    step=abs(response(baseline,m-0.5)-response(baseline,m+0.5))
    return dict(response_lower=lower,response_upper=upper,response_step_pp=step,
                resolution_limited=max(center-lower,upper-center)>abs(center)*0.2)

def signal_statistics(baseline, counts, modern=False, guarded=False, stationary=False):
    values = [capacitance_change(baseline, n) for n in counts]
    mean = sum(values) / len(values)
    k = min(5, len(values)//2)
    drift = abs(sum(values[-k:])/k - sum(values[:k])/k) if k else 0
    index = max(0, min(100, mean / capacitance_change(baseline, baseline-30)*100)) if baseline > 30 else 0
    if modern:
        index=median(100*(1-((n+170)/(baseline+170))**2) for n in counts)
    edge=min(counts)
    quantum=abs(capacitance_change(baseline,edge-0.5)-capacitance_change(baseline,edge+0.5))
    precision=response_precision(baseline,counts) if guarded else {}
    if guarded:
        limit=min(1,max(quantum,abs(mean)*0.15))
        if stationary and k > 1:
            def sd(xs):
                avg=sum(xs)/len(xs)
                return math.sqrt(sum((x-avg)**2 for x in xs)/(len(xs)-1))
            # Engineering tolerance, not a clinical bound or confidence interval.
            limit=min(limit,max(quantum,3*max(sd(values[:k]),sd(values[-k:]))))
        precision['drift_limit_pp']=limit
    return dict(**precision,capacitance_change_percent=mean, capacitance_range_pp=max(values)-min(values),
                capacitance_stddev_pp=math.sqrt(sum((x-mean)**2 for x in values)/len(values)),
                capacitance_drift_pp=drift, experimental_index=index, index_saturated=index >= 100,
                signal_policy='skin-contact-fraction-v1' if modern else POLICY)
