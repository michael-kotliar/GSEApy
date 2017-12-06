# -*- coding: utf-8 -*-

from __future__ import  division

import sys, logging
import numpy as np
from functools import reduce
from multiprocessing import Pool
from copy import deepcopy

def enrichment_score(gene_list, gene_set, weighted_score_type=1, correl_vector=None, esnull=None, rs=np.random.RandomState()):
    """This is the most important function of GSEAPY. It has the same algorithm with GSEA.

    :param gene_list:       The ordered gene list gene_name_list, rank_metric['gene_name']
    :param gene_set:        gene_sets in gmt file, please used gsea_gmt_parser to get gene_set.
    :param weighted_score_type:  It's indentical to gsea's weighted_score method. weighting by the correlation
                            is a very reasonable choice that allows significant gene sets with less than perfect coherence.
                            options: 0(classic),1,1.5,2. default:1. if one is interested in penalizing sets for lack of
                            coherence or to discover sets with any type of nonrandom distribution of tags, a value p < 1
                            might be appropriate. On the other hand, if one uses sets with largenumber of genes and only
                            a small subset of those is expected to be coherent, then one could consider using p > 1.
                            Our recommendation is to use p = 1 and use other settings only if you are very experienced
                            with the method and its behavior.

    :param correl_vector:   A vector with the correlations (e.g. signal to noise scores) corresponding to the genes in
                            the gene list. Or rankings, rank_metric['rank'].values
    :param esnull:          Only used this paramter when computing esnuall for statistial testing. set the esnull value
                            equal to the permutation number.
    :param rs:              Random state for initialize gene list shuffling. Default: np.random.RandomState(seed=None)

    :return:

     ES: Enrichment score (real number between -1 and +1)

     hit_index: index of a gene in gene_list, if gene included in gene_set.

     RES: Numerical vector containing the running enrichment score for all locations in the gene list .

    """

    axis = 0
    N = len(gene_list)
    #Test whether each element of a 1-D array is also present in a second array
    #It's more intuitived here than orginal enrichment_score source code.
    #use .astype to covert bool to intergers
    tag_indicator = np.in1d(gene_list, gene_set, assume_unique=True)  # notice that the sign is 0 (no tag) or 1 (tag)

    if (weighted_score_type == 0 ):
        correl_vector = np.repeat(1, N)
    else:
        correl_vector = np.abs(correl_vector)**weighted_score_type

    #get indices of tag_indicator
    hit_ind = np.flatnonzero(tag_indicator).tolist()

    # if used for compute esnull, set esnull equal to permutation number, e.g. 1000
    # else just compute enrichment scores
    if esnull:
        # set axis to 1, because we have 2 dimentional array
        axis = 1
        tag_indicator = np.tile(tag_indicator, (esnull,1))
        correl_vector = np.tile(correl_vector,(esnull,1))
        # gene list permutation
        for i in range(esnull): rs.shuffle(tag_indicator[i])
        # np.apply_along_axis(rs.shuffle, 1, tag_indicator)

    Nhint = np.sum(tag_indicator, axis=axis, keepdims=True)
    sum_correl_tag = np.sum(correl_vector*tag_indicator, axis=axis, keepdims=True)
    #compute ES score, the code below is identical to gsea enrichment_score method.
    no_tag_indicator = 1 - tag_indicator
    Nmiss =  N - Nhint
    norm_tag =  1.0/sum_correl_tag
    norm_no_tag = 1.0/Nmiss

    RES = np.cumsum(tag_indicator * correl_vector * norm_tag - no_tag_indicator * norm_no_tag, axis=axis)
    max_ES, min_ES =  np.max(RES, axis=axis), np.min(RES, axis=axis)
    es = np.where(np.abs(max_ES) > np.abs(min_ES), max_ES, min_ES)

    if esnull:
        return es.tolist()

    return es.tolist(), hit_ind, RES.tolist()

def enrichment_score_tensor(gene_mat, cor_mat, gene_sets, weighted_score_type, nperm=1000,
                            scale=True, single=False, rs=np.random.RandomState()):
    """
    Given a gene set, a map of gene names to rank levels, and a weight score, returns the ssGSEA
    enrichment score for the gene set as described by *D. Barbie et al 2009*

    ssGSEA  allows one to define an enrichment score that represents the degree of absolute enrichment
    of a gene set in each sample within a given data set.
    The  enrichment score was produced using the Empirical Cumulative Distribution Functions (ECDF)
    of the genes in the signature and the remaining genes.

    :requires: every member of gene_set is a key in rnkseries
    :param gene_sets: gmt file dict.
    :param rnk_series: pd.Series, an indexed series with rank values.
    :param weighted_score_type: the weighted exponent on the :math:`P^W_G` term.
    :param scale: If True, normalize the scores by number of genes in the gene sets.
    :returns:
             ES: Enrichment score (real number between -1 and +1),take the sum of all values in the RES array .

             hit_index: index of a gene in gene_list, if gene included in gene_set.

             RES: Numerical vector containing the running enrichment score for all locations in the gene list .

    """

    # gene_mat -> 1d: prerank, ssSSEA or 2d: GSEA
    keys_sorted = gene_mat
    keys = sorted(gene_sets.keys())

    if weighted_score_type == 0:
        # don't bother doing calcuation, just set to 1
        cor_mat = np.repeat(1, N)
    elif weighted_score_type > 0:
        pass
    else:
        logging.error("Using negative values of weighted_score_type, not allowed")
        sys.exit(0)


    cor_mat = np.abs(cor_mat)

    if keys_sorted.ndim ==1:
        # ssGSEA or Prerank
        # M genestes by N genes
        N, M = len(keys_sorted), len(keys)
        tag_indicator = np.vstack([np.in1d(keys_sorted, gene_sets[key], assume_unique=True) for key in keys])
        #index of hits
        hit_ind = [ np.flatnonzero(tag).tolist() for tag in tag_indicator ]
        # generate permutation matrix
        perm_tag_tensor = np.repeat(tag_indicator, nperm+1).reshape((M,N,nperm+1))
        # shuffle matrix, last matrix is not shuffled
        np.apply_along_axis(lambda x: np.apply_along_axis(rs.shuffle,0,x),1, perm_tag_tensor[:,:,:-1])
        # nohits
        no_tag_tensor = 1 - perm_tag_tensor
        # calculate numerator, denominator of each gene hits
        rank_alpha = (perm_tag_tensor*cor_mat[np.newaxis,:,np.newaxis])** weighted_score_type

    elif keys_sorted.ndim == 2:
        # GSEA
        # 2d array of keys_sorted, shuffled already
        # dims are correct ?
        # (M,N,nperm+1)
        perm_tag_tensor = np.dstack([np.isin(keys_sorted, gene_sets[key], assume_unique=True) for key in keys])
        #index of hits
        # [row,col,depth] ?
        hit_ind = [ np.flatnonzero(tag).tolist() for tag in perm_tag_tensor[:,:,-1] ]
        # nohits
        no_tag_tensor = 1 - perm_tag_tensor
        # calculate numerator, denominator of each gene hits
        rank_alpha = (perm_tag_tensor*cor_mat[:,:,np.newaxis])** weighted_score_type
    else:
        logging.error("Program die because of unsupported input")
        sys.exit(0)

    # Nhint = tag_indicator.sum(1)
    # Nmiss =  N - Nhint
    axis=1
    P_GW_denominator = np.sum(rank_alpha, axis=axis, keepdims=True)
    P_NG_denominator = np.sum(no_tag_tensor, axis=axis, keepdims=True)
    REStensor = np.cumsum(rank_alpha / P_GW_denominator - no_tag_tensor / P_NG_denominator, axis=axis)
    # scale es by gene numbers ?
    # https://gist.github.com/gaoce/39e0907146c752c127728ad74e123b33
    if scale: REStensor = REStensor / len(keys_sorted)
    if single:
        #ssGSEA
        esmatrix = np.sum(REStensor, axis=axis)
    else:
        #GSEA
        esmax, esmin = REStensor.max(axis=axis), REStensor.min(axis=axis)
        esmatrix = np.where(np.abs(esmax)>np.abs(esmin), esmax, esmin)

    es, esnull = esmatrix[:,-1], esmatrix[:,:-1]
    RES = REStensor[:,:,-1]

    return es, esnull, hit_ind, RES


def rank_metric_tensor(exprs, method, permutation_num, pos, neg, classes,
                       ascending, rs=np.random.RandomState()):
    """build correlation ranking tensor when permutation_type eq to phenotype"""

    # N: samples, M: gene number
    N, M = exprs.shape
    genes = exprs.index.values
    expr_mat = exprs.values.T
    # for 3d tensor, 1st dim is depth, 2nd dim is row, 3rd dim is column
    # so shape attr of ndarry on the 3d tensor, is (depth, rows, columns)
    # while axis is (0,1,2) and slcing order is [0, 1, 2]
    perm_genes_mat = np.tile(genes, (permutation_num+1,1))
    perm_cor_tensor = np.tile(expr_mat, (permutation_num+1,1,1))
    # random shuffle on the first dim along the depth dim
    # shuffle matrix, last matrix is not shuffled
    for arr in perm_cor_tensor[:-1]: rs.shuffle(arr)
    classes = np.array(classes)
    pos = classes == pos
    neg = classes == neg
    pos_cor_mean = perm_cor_tensor[:,pos,:].mean(axis=1)
    neg_cor_mean = perm_cor_tensor[:,neg,:].mean(axis=1)
    pos_cor_std = perm_cor_tensor[:,pos,:].std(axis=1)
    neg_cor_std = perm_cor_tensor[:,neg,:].std(axis=1)

    if method == 'signal_to_noise':
        cor_mat = (pos_cor_mean - neg_cor_mean)/(pos_cor_std + neg_cor_std)
    elif method == 't_test':
        denom = pos_cor_std.shape[1]
        cor_mat = (pos_cor_mean - neg_cor_mean)/ np.sqrt(pos_cor_std**2/denom + neg_cor_std**2/denom)
    elif method == 'ratio_of_classes':
        cor_mat = pos_cor_mean / neg_cor_mean
    elif method == 'diff_of_classes':
        cor_mat  = pos_cor_mean - neg_cor_mean
    elif method == 'log2_ratio_of_classes':
        cor_mat  =  np.log2(pos_cor_mean / neg_cor_mean)
    else:
        logging.error("Please provide correct method name!!!")
        sys.exit(0)

    # return matix[nperm+1, perm_cors]
    if ascending:
        cor_mat_ind = cor_mat.argsort(axis=1)
        # use .take method to use 2d indices
        genes_mat = perm_genes_mat.take(cor_mat_ind)
        cor_mat = cor_mat.take(cor_mat_ind)
    else:
        cor_mat_ind = cor_mat.argsort(axis=1)
        # use .take method to use 2d indices
        genes_mat = perm_genes_mat.take(cor_mat_ind)[:,::-1]
        cor_mat = cor_mat.take(cor_mat_ind)[:,::-1]

    return genes_mat, cor_mat

def shuffle_list(gene_list, rs=np.random.RandomState()):
    """Returns a copy of a shuffled input gene_list.

    :param gene_list: rank_metric['gene_name'].values
    :param rs: random state. Use random.Random(0) if you like.
    :return: a ranodm shuffled list.
    """

    l2 = gene_list.copy()
    rs.shuffle(l2)

    return l2

def ranking_metric(df, method, phenoPos, phenoNeg, classes, ascending):
    """The main function to rank an expression table.

   :param df:      gene_expression DataFrame.
   :param method:  The method used to calculate a correlation or ranking. Default: 'log2_ratio_of_classes'.
                   Others methods are:

                   1. 'signal_to_noise'

                      You must have at least three samples for each phenotype to use this metric.
                      The larger the signal-to-noise ratio, the larger the differences of the means (scaled by the standard deviations);
                      that is, the more distinct the gene expression is in each phenotype and the more the gene acts as a “class marker.”

                   2. 't_test'

                      Uses the difference of means scaled by the standard deviation and number of samples.
                      Note: You must have at least three samples for each phenotype to use this metric.
                      The larger the tTest ratio, the more distinct the gene expression is in each phenotype
                      and the more the gene acts as a “class marker.”

                   3. 'ratio_of_classes' (also referred to as fold change).

                      Uses the ratio of class means to calculate fold change for natural scale data.

                   4. 'diff_of_classes'

                      Uses the difference of class means to calculate fold change for natureal scale data

                   5. 'log2_ratio_of_classes'

                      Uses the log2 ratio of class means to calculate fold change for natural scale data.
                      This is the recommended statistic for calculating fold change for log scale data.


   :param phenoPos: one of lables of phenotype's names.
   :param phenoNeg: one of lable of phenotype's names.
   :param classes:  a list of phenotype labels, to specify which column of dataframe belongs to what catogry of phenotype.
   :param ascending:  bool or list of bool. Sort ascending vs. descending.
   :return: returns correlation to class of each variable. same format with .rnk file. gene_name in first coloum,
            correlation in second column.

    visit here for more docs: http://software.broadinstitute.org/gsea/doc/GSEAUserGuideFrame.html
    """

    A = phenoPos
    B = phenoNeg

    #exclude any zero stds.
    df_mean = df.groupby(by=classes, axis=1).mean()
    df_std =  df.groupby(by=classes, axis=1).std()


    if method == 'signal_to_noise':
        sr = (df_mean[A] - df_mean[B])/(df_std[A] + df_std[B])
    elif method == 't_test':
        sr = (df_mean[A] - df_mean[B])/ np.sqrt(df_std[A]**2/len(df_std)+df_std[B]**2/len(df_std) )
    elif method == 'ratio_of_classes':
        sr = df_mean[A] / df_mean[B]
    elif method == 'diff_of_classes':
        sr  = df_mean[A] - df_mean[B]
    elif method == 'log2_ratio_of_classes':
        sr  =  np.log2(df_mean[A] / df_mean[B])
    else:
        logging.error("Please provide correct method name!!!")
        sys.exit()
    sr.sort_values(ascending=ascending, inplace=True)
    df3 = sr.to_frame().reset_index()
    df3.columns = ['gene_name','rank']
    df3['rank2'] = df3['rank']

    return df3

def _rnknull(df, method, phenoPos, phenoNeg, classes, ascending):
    """For multiprocessing
    """
    r2 = ranking_metric(df=df, method=method, phenoPos=phenoPos,
                        phenoNeg=phenoNeg, classes=classes, ascending=ascending)
    ranking2=r2['rank'].values
    gene_list2=r2['gene_name'].values

    return ranking2, gene_list2

def gsea_compute(data, gmt, n, weighted_score_type, permutation_type, method,
                 phenoPos, phenoNeg, classes, ascending, seed, processes, scale=False, prerank=False):
    """compute enrichment scores and enrichment nulls.

    :param data: prepreocessed expression dataframe or a pre-ranked file if prerank=True.
    :param gmt: all gene sets in .gmt file. need to call gsea_gmt_parser() to get results.
    :param n: permutation number. default: 1000.
    :param method: ranking_metric method. see above.
    :param phenoPos: one of lables of phenotype's names.
    :param phenoNeg: one of lable of phenotype's names.
    :param classes: a list of phenotype labels, to specify which column of dataframe belongs to what catogry of phenotype.
    :param weighted_score_type: default:1
    :param ascending: sorting order of rankings. Default: False.
    :param seed: random seed. Default: np.random.RandomState()
    :param prerank: if true, this function will compute using pre-ranked file passed by parameter data.

    :return:
      zipped results of es, nes, pval, fdr. Used for generating reportes and plotting.

      a nested list of hit indexs of input gene_list. Used for plotting.

      a nested list of ranked enrichment score of each input gene_sets. Used for plotting.

    """

    es = []
    RES = []
    hit_ind = []
    subsets = sorted(gmt.keys())
    rs = np.random.RandomState(seed)
    # for subset in subsets:
    #     e, ind, RES = enrichment_score(gene_list, gmt.get(subset), w, ranking, None, rs)
    #     es.append(e)
    #     rank_ES.append(RES)
    #     hit_ind.append(ind)
    logging.debug("Start to compute enrichment socres......................")

    if permutation_type == "phenotype":
        #shuffling classes and generate raondom correlation rankings
        genes_mat, cor_mat = rank_metric_tensor(exprs=data, method=method,
                                                permutation_num=n,
                                                pos=phenoPos, neg=phenoNeg, classes=classes,
                                                ascending=ascending, rs=rs)
        # compute es, esnulls. hits, RES
        # gene_mat, cor_mat, gene_sets, weighted_score_type, nperm=1000,
        es, esnull, hit_ind, RES = enrichment_score_tensor(gene_mat=genes_mat,cor_mat=cor_mat,
                                                           gene_sets=gmt,
                                                           weighted_score_type=weighted_score_type,
                                                           nperm=n, scale=False,
                                                           single=False, rs=rs)
        # rank_nulls=[]
        # pool_rnkn = Pool(processes=processes)
        # for i in range(n):
        #     #you have to reseed, or all your processes are sharing the same seed value
        #     #rs = np.random.RandomState(seed)
        #     rs = np.random.RandomState()
        #     rs.shuffle(l2)
        #     l3 = deepcopy(l2)
        #     rank_nulls.append(pool_rnkn.apply_async(_rnknull, args=(dat2, method,
        #                                                           phenoPos, phenoNeg,
        #                                                           l3, ascending)))
        # pool_rnkn.close()
        # pool_rnkn.join()
        #
        # for temp_rnk in rank_nulls:
        #     rnkn, gl = temp_rnk.get()
        #     for si, subset in enumerate(subsets):
        #         esn = enrichment_score(gene_list=gl, gene_set=gmt.get(subset),
        #                                weighted_score_type=w, correl_vector=rnkn, esnull=None, rs=rs)[0]
        #         esnull[si].append(esn)
    else:
        keys_sorted = data.index.values
        if not prerank:
            data = ranking_metric(df=data, method=method, phenoPos=phenoPos,
                                     phenoNeg=phenoNeg, classes=classes, ascending=ascending)
        cor_vec = data['rank'].values
        es, esnull, hit_ind, RES = enrichment_score_tensor(gene_mat=keys_sorted, cor_mat=cor_vec,
                                                           gene_sets=gmt,
                                                           weighted_score_type=weighted_score_type,
                                                           nperm=n, scale=False,
                                                           single=False, rs=rs)
        # #multi-threading for esnulls.
        # temp_esnu=[]
        # pool_esnu = Pool(processes=processes)
        # for subset in subsets:
        #     #you have to reseed, or all your processes are sharing the same seed value
        #     #rs = np.random.RandomState(seed)
        #     rs = np.random.RandomState()
        #     temp_esnu.append(pool_esnu.apply_async(enrichment_score, args=(gene_list, gmt.get(subset), w,
        #                                                                    ranking, n, rs)))
        #
        # pool_esnu.close()
        # pool_esnu.join()
        # # esn is a list, don't need to use append method.
        # for si, temp in enumerate(temp_esnu):
        #     enrichment_nulls[si] = temp.get()
    return gsea_significance(es, esnull), hit_ind, RES, subsets

def gsea_compute_ss(data, gmt, n, weighted_score_type, scale, seed, processes=1):
    """compute enrichment scores and enrichment nulls for single sample GSEA.
    """
    subsets = sorted(gmt.keys())
    logging.debug("Start to compute enrichment socres......................")
    rs = np.random.RandomState(seed)
    # data is a pd.Series
    keys_sorted = data.index.values
    cor_vec = data.values
    es, esnull, hit_ind, RES = enrichment_score_tensor(gene_mat=keys_sorted,cor_mat=cor_vec,
                                                       gene_sets=gmt,
                                                       weighted_score_type=weighted_score_type,
                                                       nperm=n, scale=False,
                                                       single=True, rs=rs)

    return gsea_significance(es, esnull), hit_ind, RES, subsets

def gsea_pval(es, esnull):
    """Compute nominal p-value.

    From article (PNAS):
    estimate nominal p-value for S from esnull by using the positive
    or negative portion of the distribution corresponding to the sign
    of the observed ES(S).
    """

    # to speed up, using numpy function to compute pval in parallel.
    es = np.array(es)
    esnull = np.array(esnull)
    #try:
    condlist = [ es < 0, es >=0]
    choicelist = [np.sum(esnull < es.reshape(len(es),1), axis=1)/ np.sum(esnull < 0, axis=1),
                  np.sum(esnull >= es.reshape(len(es),1), axis=1)/ np.sum(esnull >= 0, axis=1)]
    pval = np.select(condlist, choicelist)

    return pval
    #except:
    #    return np.repeat(1.0 ,len(es))



def normalize(es, enrNull):
    """normalize the ES(S,pi) and the observed ES(S), separetely rescaling
       the positive and negative scores by divident by the mean of the ES(S,pi).
    """

    try:
        if es == 0:
            return 0.0
        if es >= 0:
            meanPos = np.mean([a for a in enrNull if a >= 0])
            #print es, meanPos
            return es/meanPos
        else:
            meanNeg = np.mean([a for a in enrNull if a < 0])
            #print es, meanNeg
            return -es/meanNeg
    except:
        return 0.0 #return if according mean value is uncalculable


def gsea_significance(enrichment_scores, enrichment_nulls):
    """Compute nominal p-vals, normalized ES, and FDR q value.

        For a given NES(S) = NES* >= 0. The FDR is the ratio of the percantage of all (S,pi) with
        NES(S,pi) >= 0, whose NES(S,pi) >= NES*, divided by the percentage of
        observed S wih NES(S) >= 0, whose NES(S) >= NES*, and similarly if NES(S) = NES* <= 0.
    """

    logging.debug("Start to compute pvals..................................")
    #compute pvals.
    enrichmentPVals = gsea_pval(enrichment_scores, enrichment_nulls).tolist()

    #new normalize enrichment score calculating method. this could speed up significantly.
    esnull_meanPos = []
    esnull_meanNeg = []

    es = np.array(enrichment_scores)
    esnull = np.array(enrichment_nulls)

    for i in range(len(enrichment_scores)):
        enrNull = esnull[i]
        meanPos = enrNull[enrNull >= 0].mean()
        esnull_meanPos.append(meanPos)
        meanNeg = enrNull[enrNull < 0 ].mean()
        esnull_meanNeg.append(meanNeg)

    pos = np.array(esnull_meanPos).reshape(len(es), 1)
    neg = np.array(esnull_meanNeg).reshape(len(es), 1)

    #compute normalized enrichment score and normalized esnull
    logging.debug("Compute normalized enrichment score and normalized esnull")

    try:
        condlist1 = [ es >= 0, es < 0]
        choicelist1 = [ es/esnull_meanPos, -es/esnull_meanNeg ]
        nEnrichmentScores = np.select(condlist1, choicelist1).tolist()

        condlist2 = [ esnull >= 0, esnull < 0]
        choicelist2 = [ esnull/pos, -esnull/neg ]
        nEnrichmentNulls = np.select(condlist2, choicelist2)

    except:  #return if according nes, nesnull is uncalculable
        nEnrichmentScores = np.repeat(0.0, es.size).tolist()
        nEnrichmentNulls = np.repeat(0.0 , es.size).reshape(esnull.shape)


    logging.debug("start to compute fdrs..................................")

    #FDR null distribution histogram
    #create a histogram of all NES(S,pi) over all S and pi
    #Use this null distribution to compute an FDR q value,
    # vals = reduce(lambda x,y: x+y, nEnrichmentNulls, [])
    # nvals = np.array(sorted(vals))
    # or
    nvals = np.sort(nEnrichmentNulls.flatten())
    nnes = np.array(sorted(nEnrichmentScores))
    fdrs = []
    # FDR computation
    for i in range(len(enrichment_scores)):
        nes = nEnrichmentScores[i]

        if nes >= 0:
            allPos = int(len(nvals) - np.searchsorted(nvals, 0, side="left"))
            allHigherAndPos = int(len(nvals) - np.searchsorted(nvals, nes, side="left"))
            nesPos = len(nnes) - int(np.searchsorted(nnes, 0, side="left"))
            nesHigherAndPos = len(nnes) - int(np.searchsorted(nnes, nes, side="left"))
        else:
            allPos = int(np.searchsorted(nvals, 0, side="left"))
            allHigherAndPos = int(np.searchsorted(nvals, nes, side="right"))
            nesPos = int(np.searchsorted(nnes, 0, side="left"))
            nesHigherAndPos = int(np.searchsorted(nnes, nes, side="right"))
        try:
            pi_norm = allHigherAndPos/float(allPos) #p value
            pi_obs = nesHigherAndPos/float(nesPos)

            fdr = pi_norm/pi_obs if pi_norm/pi_obs < 1.0  else 1.0
            fdrs.append(fdr)
        except:
            fdrs.append(1000000000.0)

    logging.debug("Statistial testing finished.............................")

    return zip(enrichment_scores, nEnrichmentScores, enrichmentPVals, fdrs)
