from __future__ import print_function
import numpy as np

import regreg.api as rr
import selection.tests.reports as reports


from selection.tests.flags import SET_SEED, SMALL_SAMPLES
from selection.tests.instance import logistic_instance, gaussian_instance
from selection.tests.decorators import (wait_for_return_value,
                                        set_seed_iftrue,
                                        set_sampling_params_iftrue,
                                        register_report)
import selection.tests.reports as reports

from selection.api import (randomization,
                           glm_group_lasso,
                           glm_group_lasso_parametric,
                           multiple_queries,
                           glm_target)
from statsmodels.sandbox.stats.multicomp import multipletests
from selection.randomized.cv_view import CV_view


@register_report(['pvalue', 'active_var'])
@set_sampling_params_iftrue(SMALL_SAMPLES, ndraw=10, burnin=10)
@set_seed_iftrue(SET_SEED)
@wait_for_return_value()
def test_power(s=10,
               n=3000,
               p=1000,
               rho=0.,
               snr=3.5,
               lam_frac = 1.,
               q = 0.2,
               cross_validation = True,
               randomizer = 'gaussian',
               randomizer_scale = 1.,
               ndraw=20000,
               burnin=2000,
               loss='gaussian',
               scalings=False,
               subgrad =True,
               parametric=True):


    if loss=="gaussian":
        X, y, beta, nonzero, sigma = gaussian_instance(n=n, p=p, s=s, rho=rho, snr=snr, sigma=1)
        lam = np.mean(np.fabs(np.dot(X.T, np.random.standard_normal((n, 2000)))).max(0)) * sigma
        glm_loss = rr.glm.gaussian(X, y)
    elif loss=="logistic":
        X, y, beta, _ = logistic_instance(n=n, p=p, s=s, rho=rho, snr=snr)
        glm_loss = rr.glm.logistic(X, y)
        lam = np.mean(np.fabs(np.dot(X.T, np.random.binomial(1, 1. / 2, (n, 10000)))).max(0))

    if randomizer =='laplace':
        randomizer = randomization.laplace((p,), scale=randomizer_scale)
    elif randomizer=='gaussian':
        randomizer = randomization.isotropic_gaussian((p,), scale=randomizer_scale)

    epsilon = 1. / np.sqrt(n)

    views = []
    if cross_validation:
        cv = CV_view(glm_loss, lasso_randomization=randomizer, epsilon=epsilon, loss=loss,
                     scale1=0.1, scale2=0.1)
        #views.append(cv)
        cv.solve()
        lam = cv.lam_CVR
        print("minimizer of CVR", lam)

        condition_on_CVR = True
        if condition_on_CVR:
            cv.condition_on_opt_state()
            lam = cv.one_SD_rule()
            print("one SD rule lambda", lam)

        #from selection.randomized.cv import CV
        #lam_seq = np.exp(np.linspace(np.log(1.e-6), np.log(2), 30)) * np.mean(np.fabs(np.dot(X.T, y).max(0)))
        #K = 5
        #folds = np.arange(n) % K
        #np.random.shuffle(folds)
        #CV_compute = CV(glm_loss, folds, lam_seq)
        #_, _, lam, _ = CV_compute.choose_lambda_CVr(scale=0.5)
        #lam = (lam+np.mean(np.fabs(randomizer.sample((1000,))).max(0)))/np.sqrt(2)

    W = lam_frac * np.ones(p) * lam
    penalty = rr.group_lasso(np.arange(p), weights=dict(zip(np.arange(p), W)), lagrange=1.)

    if parametric == False:
        Mest = glm_group_lasso(glm_loss, epsilon, penalty, randomizer)
    else:
        Mest = glm_group_lasso_parametric(glm_loss, epsilon, penalty, randomizer)

    views.append(Mest)

    queries = multiple_queries(views)
    queries.solve()

    active_union = np.zeros(p, np.bool)
    active_union += Mest.selection_variable['variables']

    nactive = np.sum(active_union)
    print("nactive", nactive)
    if nactive==0:
        return None

    nonzero = np.where(beta)[0]
    true_vec = beta[active_union]

    active_set = np.nonzero(active_union)[0]
    print("active set", active_set)
    print("true nonzero", np.nonzero(beta)[0])

    check_screen = False
    if check_screen==False:

        if scalings: # try condition on some scalings
             Mest.condition_on_scalings()
        if subgrad:
             Mest.decompose_subgradient(conditioning_groups=np.zeros(p, dtype=bool), marginalizing_groups=np.ones(p, bool))

        active_set = np.nonzero(active_union)[0]
        active_var = np.zeros(nactive, np.bool)
        for j in range(nactive):
            active_var[j] = active_set[j] in nonzero

        target_sampler, target_observed = glm_target(glm_loss,
                                                     active_union,
                                                     queries,
                                                     bootstrap=False,
                                                     parametric=parametric)
                                                     #reference= beta[active_union])
        target_sample = target_sampler.sample(ndraw=ndraw,
                                              burnin=burnin)
        pvalues = target_sampler.coefficient_pvalues(target_observed,
                                                     parameter=np.zeros_like(target_observed),
                                                     sample=target_sample)
        return pvalues, active_var, s


def BH(pvalues, active_var, s, q=0.2):
    decisions = multipletests(pvalues, alpha=q, method="fdr_bh")[0]
    TP = decisions[active_var].sum()
    FDP = np.true_divide(decisions.sum() - TP, max(decisions.sum(), 1))
    power = np.true_divide(TP, s)
    total_rejections = decisions.sum()
    false_rejections = total_rejections - TP
    return FDP, power, total_rejections, false_rejections

def simple_rejections(pvalues, active_var, s, alpha=0.05):
    decisions = (pvalues < alpha)
    TP = decisions[active_var].sum()
    FDP = np.true_divide(decisions.sum() - TP, max(decisions.sum(), 1))
    nactive = active_var.shape[0]
    FP = np.true_divide(decisions.sum() - TP, nactive)
    power = np.true_divide(TP, s)
    total_rejections = decisions.sum()
    false_rejections = total_rejections - TP
    # selected and survived
    survived = np.true_divide(TP, active_var.sum())
    return FP, FDP, power, total_rejections, false_rejections, nactive, survived


def report(niter=50, **kwargs):

    condition_report = reports.reports['test_power']
    runs = reports.collect_multiple_runs(condition_report['test'],
                                         condition_report['columns'],
                                         niter,
                                         reports.summarize_all,
                                         **kwargs)

    fig = reports.pivot_plot_simple(runs)
    fig.savefig('marginalized_subgrad_pivots.pdf')


def compute_power():
    BH_sample, simple_rejections_sample = [], []
    niter = 200
    for i in range(niter):
        print("iteration", i)
        result = test_power()[1]
        if result is not None:
            pvalues, active_var, s = result
            BH_sample.append(BH(pvalues, active_var,s))
            simple_rejections_sample.append(simple_rejections(pvalues, active_var,s))

        print("FDP BH mean", np.mean([i[0] for i in BH_sample]))
        print("power BH mean", np.mean([i[1] for i in BH_sample]))
        print("total rejections BH", np.mean([i[2] for i in BH_sample]))
        print("false rejections BH ", np.mean([i[3] for i in BH_sample]))

        print("FP level mean", np.mean([i[0] for i in simple_rejections_sample]))
        print("FDP level mean", np.mean([i[1] for i in simple_rejections_sample]))
        print("power level mean", np.mean([i[2] for i in simple_rejections_sample]))
        print("total rejections level", np.mean([i[3] for i in simple_rejections_sample]))
        print("false rejections level", np.mean([i[4] for i in simple_rejections_sample]))
        print("nactive mean", np.mean([i[5] for i in simple_rejections_sample]))
        print("true variables that survived the second round", np.mean([i[6] for i in simple_rejections_sample]))

    return None


if __name__ == '__main__':
    compute_power()
