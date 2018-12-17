"""
The data_cleaner module is used to clean missing or NaN values from pandas
dataframes (e.g. removing NaN, imputation, etc.)
"""

import pandas as pd
import numpy as np
import logging
import os

from sklearn.preprocessing import Imputer
from scipy.linalg import orth

log = logging.getLogger('mastml')


def remove(df, axis):
    """
    Method that removes a full column or row of data values if one column or
    row contains NaN or is blank

    Args:
        df: (dataframe), pandas dataframe containing data
        axis: (int), whether to remove rows (axis=0) or columns (axis=1)

    Returns:
        df: (dataframe): dataframe with NaN or missing values removed

    """
    # TODO: add cleaning for y data (remove rows, and need to remove rows from
    #  other df's as well
    # df_nan = df[pd.isnull(df)]
    # nan_indices = df_nan.index
    # print(nan_indices)
    df = df.dropna(axis=axis, how='any')
    return df


def imputation(df, strategy, cols_to_leave_out=None):
    """
    Method that imputes values to the missing places based on the median, mean,
    etc. of the data in the column

    Args:
        df: (dataframe), pandas dataframe containing data
            strategy: (str), method of imputation, e.g. median, mean, etc.
        cols_to_leave_out: (list), list of column indices to not include in
                           imputation

    Returns:
        df: (dataframe), dataframe with NaN or missing values resolved via
            imputation

    """

    imputervals = Imputer(
                          missing_values='NaN',
                          strategy=strategy,
                          axis=0
                          )

    if cols_to_leave_out is None:
        df_imputed = pd.DataFrame(imputervals.fit_transform(df))
    else:
        imputervals = imputervals.fit_transform(df.drop(
                                                        cols_to_leave_out,
                                                        axis=1
                                                        ))
        df_imputed = pd.DataFrame(imputervals)

    # Need to join the imputed dataframe with the columns containing strings
    # that were held out
    if cols_to_leave_out is None:
        df = df_imputed
    else:
        df = pd.concat([df_imputed, df[cols_to_leave_out]], axis=1)
    return df


def ppca(df, cols_to_leave_out=None):
    """
    Method that performs a recursive PCA routine to use PCA of known columns
    to fill in missing values in particular column

    Args:
        df: (dataframe), pandas dataframe containing data
            cols_to_leave_out: (list), list of column indices to not include
            in imputation

    Returns:
        df: (dataframe), dataframe with NaN or missing values resolved via
            imputation

    """
    pca_magic = PPCA()
    if cols_to_leave_out is None:
        pca_magic.fit(np.array(df))
    else:
        pca_magic.fit(np.array(df.drop(cols_to_leave_out, axis=1)))
    # Need to un-standardize the pca-transformed data
    df_ppca = pd.DataFrame(pca_magic.data*pca_magic.stds+pca_magic.means)
    if cols_to_leave_out is None:
        df = df_ppca
    else:
        df = pd.concat([df_ppca, df[cols_to_leave_out]], axis=1)
    return df


def columns_with_strings(df):
    """
    Method that ascertains which columns in data contain string entries

    Args:
        df: (dataframe), pandas dataframe containing data

    Returns:
        str_columns: (list), list containing indices of columns containing
        strings

    """
    str_summary = pd.DataFrame(df.applymap(type).eq(str).any())
    str_columns = str_summary.index[str_summary[0] is True].tolist()
    return str_columns


class PPCA():
    """
    Class to perform probabilistic principal component analysis (PPCA) to fill
    in missing data.

    This PPCA routine was taken directly from
    https://github.com/allentran/pca-magic.

    Due to import errors, for ease of use we have elected to copy the module
    here. This github repo was last accessed on 8/27/18. The code comprising
    the PPCA class below was not developed by and is not owned by the
    University of Wisconsin-Madison MAST-ML development team.

    """
    def __init__(self):

        self.raw = None
        self.data = None
        self.C = None
        self.means = None
        self.stds = None
        self.eig_vals = None

    def _standardize(self, X):

        if self.means is None or self.stds is None:
            raise RuntimeError("Fit model first")

        return (X - self.means) / self.stds

    def fit(self, data, d=None, tol=1e-4, min_obs=10, verbose=False):

        self.raw = data
        self.raw[np.isinf(self.raw)] = np.max(self.raw[np.isfinite(self.raw)])

        valid_series = np.sum(~np.isnan(self.raw), axis=0) >= min_obs

        data = self.raw[:, valid_series].copy()
        N = data.shape[0]
        D = data.shape[1]

        self.means = np.nanmean(data, axis=0)
        self.stds = np.nanstd(data, axis=0)

        data = self._standardize(data)
        observed = ~np.isnan(data)
        missing = np.sum(~observed)
        data[~observed] = 0

        # initial

        if d is None:
            d = data.shape[1]

        if self.C is None:
            C = np.random.randn(D, d)
        else:
            C = self.C
        CC = np.dot(C.T, C)
        X = np.dot(np.dot(data, C), np.linalg.inv(CC))
        recon = np.dot(X, C.T)
        recon[~observed] = 0
        ss = np.sum((recon - data) ** 2) / (N * D - missing)

        v0 = np.inf
        counter = 0

        while True:

            Sx = np.linalg.inv(np.eye(d) + CC / ss)

            # e-step
            ss0 = ss
            if missing > 0:
                proj = np.dot(X, C.T)
                data[~observed] = proj[~observed]
            X = np.dot(np.dot(data, C), Sx) / ss

            # m-step
            XX = np.dot(X.T, X)
            C = np.dot(np.dot(data.T, X), np.linalg.pinv(XX + N * Sx))
            CC = np.dot(C.T, C)
            recon = np.dot(X, C.T)
            recon[~observed] = 0
            ss = (np.sum((recon-data)**2)+N*np.sum(CC*Sx)+missing*ss0)/(N*D)

            # calc diff for convergence
            det = np.log(np.linalg.det(Sx))
            if np.isinf(det):
                det = abs(np.linalg.slogdet(Sx)[1])
            v1 = (
                  N * (D * np.log(ss) + np.trace(Sx) - det) +
                  np.trace(XX) - missing * np.log(ss0)
                  )

            diff = abs(v1 / v0 - 1)
            if verbose:
                print(diff)
            if (diff < tol) and (counter > 5):
                break

            counter += 1
            v0 = v1

        C = orth(C)
        vals, vecs = np.linalg.eig(np.cov(np.dot(data, C).T))
        order = np.flipud(np.argsort(vals))
        vecs = vecs[:, order]
        vals = vals[order]

        C = np.dot(C, vecs)

        # attach objects to class
        self.C = C
        self.data = data
        self.eig_vals = vals
        self._calc_var()

    def transform(self, data=None):

        if self.C is None:
            raise RuntimeError('Fit the data model first.')
        if data is None:
            return np.dot(self.data, self.C)
        return np.dot(data, self.C)

    def _calc_var(self):

        if self.data is None:
            raise RuntimeError('Fit the data model first.')

        data = self.data.T

        # variance calc
        var = np.nanvar(data, axis=1)
        total_var = var.sum()
        self.var_exp = self.eig_vals.cumsum() / total_var

    def save(self, fpath):

        np.save(fpath, self.C)

    def load(self, fpath):

        assert os.path.isfile(fpath)

        self.C = np.load(fpath)
