from __future__ import print_function
import functools
import numpy as np
from scipy.stats import norm as ndist

import regreg.api as rr

from ..constraints.affine import constraints
from .query import (query, 
                    affine_gaussian_sampler)
from .randomization import randomization
from ..algorithms.debiased_lasso import debiasing_matrix

class screening(query):

    def __init__(self,
                 observed_data,
                 covariance, 
                 randomizer,
                 perturb=None):

        self.observed_score_state = -observed_data  # -Z if Z \sim N(\mu,\Sigma), X^Ty in regression setting
        self.nfeature = p = self.observed_score_state.shape[0]
        self.covariance = covariance
        self.randomizer = randomizer
        self._initial_omega = perturb

    def fit(self, perturb=None):

        p = self.nfeature

        # take a new perturbation if supplied
        if perturb is not None:
            self._initial_omega = perturb
        if self._initial_omega is None:
            self._initial_omega = self.randomizer.sample()

        _randomized_score = self.observed_score_state - self._initial_omega
        active = np.fabs(_randomized_score) >= self.threshold

        self._selected = active
        self._not_selected = ~self._selected
        sign = np.sign(-_randomized_score)
        active_signs = sign[self._selected]
        sign[self._not_selected] = 0
        self.selection_variable = {'sign': sign,
                                   'variables': self._selected.copy()}

        self.observed_opt_state = (np.fabs(_randomized_score) - self.threshold)[self._selected]
        self.num_opt_var = self.observed_opt_state.shape[0]

        opt_linear = np.zeros((p, self.num_opt_var))
        opt_linear[self._selected,:] = np.diag(active_signs)
        opt_offset = np.zeros(p)
        opt_offset[self._selected] = active_signs * self.threshold[self._selected]
        opt_offset[self._not_selected] = _randomized_score[self._not_selected]

        self._setup = True

        A_scaling = -np.identity(len(active_signs))
        b_scaling = np.zeros(self.num_opt_var)

        self._set_sampler(A_scaling,
                          b_scaling,
                          opt_linear,
                          opt_offset)

        return self._selection

    def multivariate_targets(self, features, dispersion=1.):
        """
        Entries of the mean of \Sigma[E,E]^{-1}Z_E
        """
        score_linear = self.covariance[:, features].copy() / dispersion
        Q = score_linear[features]
        cov_target = np.linalg.inv(Q)
        observed_target = -np.linalg.inv(Q).dot(self.observed_score_state[features])
        crosscov_target_score = -score_linear.dot(cov_target)
        alternatives = ['twosided'] * features.sum()

        return observed_target, cov_target * dispersion, crosscov_target_score.T * dispersion, alternatives

    def marginal_targets(self, features):
        """
        Entries of the mean of Z_E
        """
        score_linear = self.covariance[:, features]
        Q = score_linear[features]
        cov_target = Q
        observed_target = -self.observed_score_state[features]
        crosscov_target_score = -score_linear
        alternatives = ['twosided'] * features.sum()

        return observed_target, cov_target, crosscov_target_score.T, alternatives

    # Private methods

    def _set_sampler(self, 
                     A_scaling,
                     b_scaling,
                     opt_linear,
                     opt_offset):

        _, prec = self.randomizer.cov_prec

        if np.asarray(prec).shape in [(), (0,)]:
            cond_precision = opt_linear.T.dot(opt_linear) * prec
            cond_covariance = np.linalg.inv(cond_precision)
            logdens_linear = cond_cov.dot(opt_linear.T) * prec  
        else:
            cond_precision = opt_linear.T.dot(prec.dot(opt_linear))
            cond_covariance = np.linalg.inv(cond_precision)
            logdens_linear = cond_cov.dot(opt_linear.T).dot(prec)

        cond_mean = logdens_linear.dot(-self.observed_score_state - opt_offset)
        logdens_transform = (logdens_linear, opt_offset)

        def log_density(logdens_linear, offset, cond_prec, score, opt):
            if score.ndim == 1:
                mean_term = logdens_linear.dot(score.T + offset).T
            else:
                mean_term = logdens_linear.dot(score.T + offset[:, None]).T
            arg = opt + mean_term
            return - 0.5 * np.sum(arg * cond_prec.dot(arg.T).T, 1)

        log_density = functools.partial(log_density, logdens_linear, opt_offset, cond_precision)

        affine_con = constraints(A_scaling,
                                 b_scaling,
                                 mean=cond_mean,
                                 covariance=cond_covariance)

        self.sampler = affine_gaussian_sampler(affine_con,
                                               self.observed_opt_state,
                                               self.observed_score_state,
                                               log_density,
                                               logdens_transform,
                                               selection_info=self.selection_variable)

    @staticmethod
    def type1(observed_data,
              covariance, 
              marginal_level,
              randomizer_scale,
              perturb=None):
        '''
        Threshold
        '''
        randomized_stdev = np.sqrt(np.diag(covariance) + randomizer_scale**2)
        p = covariance.shape[0]
        randomizer = randomization.isotropic_gaussian((p,), randomizer_scale)
        threshold = randomized_stdev * ndist.ppf(1. - marginal_level / 2.)

        return marginal_screening(observed_data,
                                  covariance, 
                                  threshold,
                                  randomizer,
                                  perturb=perturb)



class marginal_screening(query):

    def __init__(self,
                 observed_data,
                 covariance, 
                 threshold,
                 randomizer,
                 perturb=None):

        self.observed_score_state = -observed_data  # -Z if Z \sim N(\mu,\Sigma), X^Ty in regression setting
        self.nfeature = p = self.observed_score_state.shape[0]
        self.covariance = covariance
        self.randomizer = randomizer
        self._initial_omega = perturb
        self.threshold = threshold 

    def fit(self, perturb=None):

        p = self.nfeature

        # take a new perturbation if supplied
        if perturb is not None:
            self._initial_omega = perturb
        if self._initial_omega is None:
            self._initial_omega = self.randomizer.sample()

        _randomized_score = self.observed_score_state - self._initial_omega
        active = np.fabs(_randomized_score) >= self.threshold

        self._selected = active
        self._not_selected = ~self._selected
        sign = np.sign(-_randomized_score)
        active_signs = sign[self._selected]
        sign[self._not_selected] = 0
        self.selection_variable = {'sign': sign,
                                   'variables': self._selected.copy()}

        self.observed_opt_state = (np.fabs(_randomized_score) - self.threshold)[self._selected]
        self.num_opt_var = self.observed_opt_state.shape[0]

        opt_linear = np.zeros((p, self.num_opt_var))
        opt_linear[self._selected,:] = np.diag(active_signs)
        opt_offset = np.zeros(p)
        opt_offset[self._selected] = active_signs * self.threshold[self._selected]
        opt_offset[self._not_selected] = _randomized_score[self._not_selected]

        self.opt_transform = (opt_linear, opt_offset)
        self._setup = True

        _, prec = self.randomizer.cov_prec

        if np.asarray(prec).shape in [(), (0,)]:
            cond_precision = opt_linear.T.dot(opt_linear) * prec
            cond_cov = np.linalg.inv(cond_precision)
            logdens_linear = cond_cov.dot(opt_linear.T) * prec  
        else:
            cond_precision = opt_linear.T.dot(prec.dot(opt_linear))
            cond_cov = np.linalg.inv(cond_precision)
            logdens_linear = cond_cov.dot(opt_linear.T).dot(prec)

        cond_mean = logdens_linear.dot(-self.observed_score_state - opt_offset)
        logdens_transform = (logdens_linear, opt_offset)
        A_scaling = -np.identity(len(active_signs))
        b_scaling = np.zeros(self.num_opt_var)

        def log_density(logdens_linear, offset, cond_prec, score, opt):
            if score.ndim == 1:
                mean_term = logdens_linear.dot(score.T + offset).T
            else:
                mean_term = logdens_linear.dot(score.T + offset[:, None]).T
            arg = opt + mean_term
            return - 0.5 * np.sum(arg * cond_prec.dot(arg.T).T, 1)

        log_density = functools.partial(log_density, logdens_linear, opt_offset, cond_precision)

        affine_con = constraints(A_scaling,
                                 b_scaling,
                                 mean=cond_mean,
                                 covariance=cond_cov)

        self.sampler = affine_gaussian_sampler(affine_con,
                                               self.observed_opt_state,
                                               self.observed_score_state,
                                               log_density,
                                               logdens_transform,
                                               selection_info=self.selection_variable)
        return self._selected

    def multivariate_targets(self, features, dispersion=1.):
        """
        Entries of the mean of \Sigma[E,E]^{-1}Z_E
        """
        score_linear = self.covariance[:, features].copy() / dispersion
        Q = score_linear[features]
        cov_target = np.linalg.inv(Q)
        observed_target = -np.linalg.inv(Q).dot(self.observed_score_state[features])
        crosscov_target_score = -score_linear.dot(cov_target)
        alternatives = ['twosided'] * features.sum()

        return observed_target, cov_target * dispersion, crosscov_target_score.T * dispersion, alternatives

    def marginal_targets(self, features):
        """
        Entries of the mean of Z_E
        """
        score_linear = self.covariance[:, features]
        Q = score_linear[features]
        cov_target = Q
        observed_target = -self.observed_score_state[features]
        crosscov_target_score = -score_linear
        alternatives = ['twosided'] * features.sum()

        return observed_target, cov_target, crosscov_target_score.T, alternatives

    @staticmethod
    def type1(observed_data,
              covariance, 
              marginal_level,
              randomizer_scale,
              perturb=None):
        '''
        Threshold
        '''
        randomized_stdev = np.sqrt(np.diag(covariance) + randomizer_scale**2)
        p = covariance.shape[0]
        randomizer = randomization.isotropic_gaussian((p,), randomizer_scale)
        threshold = randomized_stdev * ndist.ppf(1. - marginal_level / 2.)

        return marginal_screening(observed_data,
                                  covariance, 
                                  threshold,
                                  randomizer,
                                  perturb=perturb)

