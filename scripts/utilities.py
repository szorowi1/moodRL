import numpy as np
import _pickle as cPickle
from scipy.special import gamma as fgamma
from scipy.stats import wald
from . psis import psisloo
              
def zscore(arr):
    return (arr - arr.mean()) / arr.std()

def inv_logit(arr):
    '''Elementwise inverse logit (logistic) function.'''
    return 1 / (1 + np.exp(-arr))

def phi_approx(arr):
    '''Elementwise fast approximation of the cumulative unit normal. 
    For details, see Bowling et al. (2009). "A logistic approximation 
    to the cumulative normal distribution."'''
    return inv_logit(0.07056 * arr ** 3 + 1.5976 * arr)

def normal_lpdf(x, mu, sd):
    return -0.5 * np.log(2*np.pi) - 0.5 * np.log(sd**2) - 0.5 * (sd**-2) * (x - mu)**2
    
def to_shape_rate(mode, sd):
    '''Convert parameters from gamma(mode, sd) to gamma(shape, rate).'''
    rate = ( mode + np.sqrt( mode**2 + 4*sd**2 ) ) / ( 2 * sd**2 )
    shape = 1 + mode * rate
    return shape, rate

def gamma_pdf(x, s, r):
    '''Probability density function for the (shape, rate)-parameterized
    gamma distribution.'''
    return r ** s / fgamma(s) * x ** (s - 1) * np.exp(-r * x)

def _shifted_wald_pdf(x, gamma, alpha, theta):
    tmp1 = alpha / np.sqrt(2 * np.pi * np.power(x-theta,3))
    tmp2 = np.power(alpha-gamma*(x-theta), 2) / (2*(x-theta))
    return tmp1 * np.exp(-1*tmp2)

def shifted_wald_pdf(x, gamma, alpha, theta):    
    p = np.zeros_like(x)
    p[np.where(x-theta>0)] = _shifted_wald_pdf(x[np.where(x-theta>0)], gamma, alpha, theta)
    return p

def shifted_wald_rng(gamma, alpha, theta, ub=np.inf, size=1):
    
    ## Convert parameters.
    mu = alpha / gamma
    lambd = alpha**2
    
    RT = []
    while np.size(RT) < size:
        rt = theta + np.random.wald(mu, lambd)
        if rt < ub: RT.append(rt)
            
    return np.array(RT)

def HDIofMCMC(arr, credMass=0.95):
    '''
    Computes highest density interval from a sample of representative values,
    estimated as shortest credible interval. Functions for computing HDI's are 
    explained in Chapter 25 of Doing Bayesian Data Analysis, Second Edition.
    
    INPUTS:
    -- arr: a vector of representative values from a probability distribution.
    -- credMass: a scalar between 0 and 1, indicating the mass within the credible
       interval that is to be estimated.
    '''
    sortedPts = np.sort(arr)
    ciIdxInc = np.ceil(credMass * len( sortedPts )).astype(int)
    nCIs = len( sortedPts ) - ciIdxInc
    ciWidth = [ sortedPts[ i + ciIdxInc ] - sortedPts[ i ] for i in np.arange(nCIs).astype(int) ]
    HDImin = sortedPts[ np.argmin( ciWidth ) ]
    HDImax = sortedPts[ np.argmin( ciWidth ) + ciIdxInc ]
    return HDImin, HDImax

def load_fit(model):
    fn = 'stan_fits/%s/StanFit.pickle' %model
    with open(fn, 'rb') as fn: fit = cPickle.load(fn)
    return fit

def _extract_log_lik(model_name, method):
    
    ## Load StanFit.
    extract = load_fit(model_name)
    
    Y_log_lik, M_log_lik = False, False
    
    if method in ['y','both']:
        
        ## Extract log-likelihood values.
        Y_log_lik = extract['Y_log_lik']
        n_samp, n_subj, n_block, n_trial = Y_log_lik.shape
        Y_log_lik = Y_log_lik.reshape(n_samp, n_subj*n_block*n_trial)
        
        ## Remove log-likelihoods corresponding to missing data.
        missing = np.where(np.sum(Y_log_lik, axis=0), False, True)
        Y_log_lik = Y_log_lik[:,~missing] 
        
    if method in ['m', 'both']:
        
        ## Extract log-likelihood values.
        M_log_lik = extract['M_log_lik']
        n_samp, n_subj, n_block, n_trial = M_log_lik.shape
        M_log_lik = M_log_lik.reshape(n_samp, n_subj*n_block*n_trial)
    
    return Y_log_lik, M_log_lik

def WAIC(log_lik):
    
    lppd = np.log( np.exp(log_lik).mean(axis=0) )
    pwaic = np.var(log_lik, axis=0)
    return lppd - pwaic
    
def model_comparison(a, b, metric='waic', on='both', verbose=False):
    
    ## Main loop.
    elppd = []
    for model_name in [a,b]:
        
        ## Extract log-likelihoods.
        yll, mll = _extract_log_lik(model_name, on)
        
        ## Define included log-likelihood.
        if on == 'y': log_lik = yll.copy()
        elif on == 'm': log_lik = mll.copy()
        else: log_lik = np.concatenate([yll, mll], axis=-1)
        
        ## Compute metric.
        if metric == 'waic':
            arr = WAIC(log_lik) 
        elif metric == 'loo':
            _, arr, _ = psisloo(log_lik)
        else:
            raise ValueError('"metric" must be "waic" or "loo"!')

        elppd.append(arr)
        
    ## Perform model comparison.
    elppd = -2 * np.array(elppd)
    m1, m2 = np.sum(elppd, axis=-1)
    se = np.sqrt( elppd.shape[-1] * np.var(np.diff(elppd, axis=0)) )
    
    ## Print results.
    if verbose:
                             
        print('Model comparison')
        print('----------------')
        print('%s[1] = %0.0f' %(metric.upper(),m1))
        print('%s[2] = %0.0f' %(metric.upper(),m2))
        print('Diff\t= %0.2f (%0.2f)' %(m1-m2, se))
    
    return m1, m2, se