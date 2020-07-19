---
title: "Smoothing can systematically bias small samples of one-dimensional biomechanical continua"
date: 2019-01-01
publishDate: 2020-07-05T06:34:43.927184Z
authors: ["Todd C. Pataky", "Mark A. Robinson", "Jos Vanrenterghem", "John H. Challis"]
publication_types: ["2"]
abstract: "The quality with which smoothing algorithms perform is often assessed in simulation by starting with a known 1D datum, adding noise, smoothing the noisy data, then quantifying the difference between the smoothed data and known datum, often using mean-square error (MSE). While effectively summarizing overall difference, MSE fails to capture localized, one-sided errors. This paper describes how smoothing noisy 1D data using a variety of algorithms can introduce systematic bias, and quantiﬁes this bias using the false positive rate (FPR): the probability that a smoothing algorithm will yield a dataset whose 1D mean differs signiﬁcantly from its true 1D datum. A simulation study was conducted involving six 1D datum continua, and four smoothing algorithms whose parameters were systematically manipulated along with sample size and noise amplitude. Approximately ten million simulation iterations were evaluated. FPRs were calculated at a ¼ 0:05, based on the calculated smoothness of the resulting datasets. Results showed that FPRs were much higher than the expected value of a, and in many cases approached 100%. FPRs were highest with aggressive smoothing parameters, large sample sizes and small noise amplitudes, irrespective of both smoothing algorithm and the 1D datum. These results suggest that smoothing 1D biomechanical data can introduce statistical bias with relatively high probability. The implications are experiment-speciﬁc because the biomechanical meaning of 1D changes can vary vastly between datasets. Smoothing-induced bias should be a cause for general concern when small 1D changes have non-trivial biomechanical consequences."
featured: false
publication: "*Journal of Biomechanics*"
url_pdf: "https://linkinghub.elsevier.com/retrieve/pii/S0021929018308339"
doi: "10.1016/j.jbiomech.2018.11.002"
projects: [spm1d]
---
