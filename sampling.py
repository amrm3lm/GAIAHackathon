
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

def get_optimal_k(start, end, embeddings):
    sil = []
    labels = []
    kmax = end

    for k in range(start, kmax + 1):
        kmeans = KMeans(n_clusters=k).fit(embeddings)
        labels.append(kmeans.labels_)
        sil.append(silhouette_score(embeddings, kmeans.labels_, metric='euclidean'))
    max_sil = sil.index(max(sil))
    return start + max_sil, labels[max_sil]


def sample(reviews, client,review_helpfullness,  max_words=1000):
    s = 2
    m = len(reviews) / 2
    response = client.embed(model='embed-english-v2.0', texts=reviews)
    best_k, best_labels = get_optimal_k(s, m, response.embeddings)
    sampled = []
    # Step 1: Group sentences by cluster labels
    cluster_dict = {}
    for i, label in enumerate(best_labels):
        if label not in cluster_dict:
            cluster_dict[label] = []
        cluster_dict[label].append((review_helpfullness[i], reviews[i]))

    # Step 3: Sort the dictionary by cluster size
    sorted_clusters = sorted(cluster_dict.items(), key=lambda x: len(x[1]), reverse=True)

    # sort each cluster by helpfullness
    for k in cluster_dict.keys():
        sorted(cluster_dict[k], reverse=True)

    # Step 4: Initialize a list for selected sentence embeddings
    selected_reviews = []

    # Step 5: Select one sentence from each cluster
    sz = 0
    cluster_num = 0
    while sz < max_words:
        selected = cluster_dict[cluster_num][0]
        # only need the review
        selected_reviews.append(selected[1])
        cluster_dict[cluster_num].pop(0)
        sz += len(selected)
        cluster_num = (cluster_num + 1) % best_k

    return selected_reviews
