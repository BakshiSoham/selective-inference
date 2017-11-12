from __future__ import print_function
import numpy as np, sys

from scipy.stats import norm as ndist
from selection.adjusted_MLE.selective_MLE import solve_UMVU
from selection.adjusted_MLE.tests.exact_MLE import grad_CGF
from statsmodels.distributions.empirical_distribution import ECDF

def simple_problem(target_observed=2, n=1, threshold=2, randomization_scale=1.):
    """
    Simple problem: randomizaiton of sd 1 and thresholded at 2 (default args)
    """
    target_observed = np.atleast_1d(target_observed)
    target_transform = (-np.identity(n), np.zeros(n))
    opt_transform = (np.identity(n), np.ones(n) * threshold)
    feasible_point = np.ones(n)
    randomizer_precision = np.identity(n) / randomization_scale ** 2
    target_cov = np.identity(n)

    return solve_UMVU(target_transform,
                      opt_transform,
                      target_observed,
                      feasible_point,
                      target_cov,
                      randomizer_precision)

def bootstrap_simple(n= 100, B=100, true_mean=0., threshold=2.):

    while True:
        Zval = np.random.normal(true_mean, 1, n)
        omega = np.random.normal(0, 1)
        target_Z = (np.sum(Zval) / np.sqrt(n))
        check = target_Z + omega - threshold
        if check>0.:
            break

    approx_MLE, value, mle_map = simple_problem(target_Z, n=1, threshold=2, randomization_scale=1.)

    boot_sample = []
    for b in range(B):
        Zval_boot = np.sum(Zval[np.random.choice(n, n, replace=True)]) / np.sqrt(n)
        boot_sample.append(mle_map(Zval_boot)[0])

    return boot_sample, np.mean(boot_sample), np.std(boot_sample), \
           np.squeeze((boot_sample - np.mean(boot_sample)) / np.std(boot_sample))

# if __name__ == "__main__":
#     n = 1000
#     Zval = np.random.normal(0, 1, n)
#     sys.stderr.write("observed Z" + str(Zval) + "\n")
#     MLE = simple_problem(Zval, n=n, threshold=2, randomization_scale=1.)[0]
#     #print(MLE)
#
#     mu_seq = np.linspace(-6, 6, 200)
#     grad_partition = np.array([grad_CGF(mu, randomization_scale=1., threshold=2) for mu in mu_seq])
#
#     exact_MLE = []
#     for k in range(Zval.shape[0]):
#         mle = mu_seq[np.argmin(np.abs(grad_partition - Zval[k]))]
#         exact_MLE.append(mle)
#
#     np.testing.assert_allclose(MLE, exact_MLE, rtol=2.0)

# if __name__ == "__main__":
#     import matplotlib.pyplot as plt
#
#     plt.clf()
#     Zval = np.linspace(-5, 5, 51)
#     MLE = np.array([simple_problem(z)[0] for z in Zval])
#
#     mu_seq = np.linspace(-6, 6, 200)
#     grad_partition = np.array([grad_CGF(mu, randomization_scale=1., threshold=2) for mu in mu_seq])
#
#     plt.plot(Zval, MLE, label='+2')
#     plt.plot(grad_partition, mu_seq, 'r--', label='MLE')
#     plt.legend()
#     plt.show()

if __name__ == "__main__":
    import matplotlib.pyplot as plt

    plt.clf()
    boot_result = bootstrap_simple(n= 100, B=1000, true_mean=1., threshold=2.)
    boot_pivot = boot_result[3]
    print("boot sample", boot_pivot.shape)
    ecdf = ECDF(ndist.cdf(boot_pivot))
    grid = np.linspace(0, 1, 101)
    print("ecdf", ecdf(grid))
    plt.plot(grid, ecdf(grid), c='red', marker='^')
    plt.show()