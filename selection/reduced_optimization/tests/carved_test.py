from __future__ import print_function
import numpy as np
import time
import regreg.api as rr
from selection.bayesian.initial_soln import selection
from selection.tests.instance import logistic_instance, gaussian_instance

from selection.reduced_optimization.par_carved_reduced import selection_probability_carved, sel_inf_carved

from selection.reduced_optimization.estimator import M_estimator_approx_carved

def carved_lasso_trial(X,
                       y,
                       beta,
                       sigma,
                       lam,
                       estimation='parametric'):
    n, p = X.shape

    loss = rr.glm.gaussian(X, y)
    epsilon = 1. / np.sqrt(n)

    W = np.ones(p) * lam
    penalty = rr.group_lasso(np.arange(p), weights=dict(zip(np.arange(p), W)), lagrange=1.)

    total_size = loss.saturated_loss.shape[0]
    subsample_size = int(0.8 * total_size)

    M_est = M_estimator_approx_carved(loss, epsilon, subsample_size, penalty, estimation)

    M_est.solve_approx()
    active = M_est._overall
    nactive = M_est.nactive

    prior_variance = 1000.
    noise_variance = sigma ** 2
    projection_active = X[:, active].dot(np.linalg.inv(X[:, active].T.dot(X[:, active])))
    M_1 = prior_variance * (X.dot(X.T)) + noise_variance * np.identity(n)
    M_2 = prior_variance * ((X.dot(X.T)).dot(projection_active))
    M_3 = prior_variance * (projection_active.T.dot(X.dot(X.T)).dot(projection_active))
    post_mean = M_2.T.dot(np.linalg.inv(M_1)).dot(y)

    print("observed data", post_mean)

    post_var = M_3 - M_2.T.dot(np.linalg.inv(M_1)).dot(M_2)

    unadjusted_intervals = np.vstack([post_mean - 1.65 * (np.sqrt(post_var.diagonal())),
                                      post_mean + 1.65 * (np.sqrt(post_var.diagonal()))])

    grad_lasso = sel_inf_carved(M_est, prior_variance)
    samples = grad_lasso.posterior_samples()
    adjusted_intervals = np.vstack([np.percentile(samples, 5, axis=0), np.percentile(samples, 95, axis=0)])

    coverage_ad = np.zeros(nactive)
    coverage_unad = np.zeros(nactive)
    nerr = 0.

    true_val = np.zeros(nactive)

    if nactive >= 1:
        try:
            for l in range(nactive):
                if (adjusted_intervals[0, l] <= true_val[l]) and (true_val[l] <= adjusted_intervals[1, l]):
                    coverage_ad[l] += 1
                if (unadjusted_intervals[0, l] <= true_val[l]) and (true_val[l] <= unadjusted_intervals[1, l]):
                    coverage_unad[l] += 1

        except ValueError:
            nerr += 1
            print('ignore iteration raising ValueError')

        sel_cov = coverage_ad.sum() / nactive
        naive_cov = coverage_unad.sum() / nactive

        return sel_cov, naive_cov

    else:
        return None


if __name__ == "__main__":
    ### set parameters
    n = 500
    p = 100
    s = 0
    snr = 0.


    niter = 10
    ad_cov = 0.
    unad_cov = 0.

    for i in range(niter):

         ### GENERATE X, Y BASED ON SEED
         np.random.seed(i+2)  # ensures different y
         X, y, beta, nonzero, sigma = gaussian_instance(n=n, p=p, s=s, sigma=1., rho=0, snr=snr)
         lam = 1. * np.mean(np.fabs(np.dot(X.T, np.random.standard_normal((n, 2000)))).max(0)) * sigma

         ### RUN LASSO AND TEST
         lasso = carved_lasso_trial(X,
                                    y,
                                    beta,
                                    sigma,
                                    lam)

         if lasso is not None:
             ad_cov += lasso[0]
             unad_cov += lasso[1]
             print("\n")
             print("iteration completed", i)
             print("\n")
             print("adjusted and unadjusted coverage", ad_cov, unad_cov)


    print("adjusted and unadjusted coverage",ad_cov, unad_cov)