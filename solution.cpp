#include <bits/stdc++.h>
using namespace std;

typedef long long ll;
typedef tuple<ll,int,int> State;

int N, M, R;
string grid[2001];  // FIX: use string instead of char array

vector<pair<ll,ll>> courses[2001][2001];

ll earliest_free(int x, int y, ll T) {
    auto& cv = courses[x][y];
    if (cv.empty()) return T;

    int lo = 0, hi = (int)cv.size() - 1, idx = -1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        if (cv[mid].first <= T) { idx = mid; lo = mid + 1; }
        else hi = mid - 1;
    }

    if (idx == -1) return T;

    if (cv[idx].second >= T) {
        T = cv[idx].second + 1;
        if (idx + 1 < (int)cv.size() && cv[idx+1].first <= T) {
            T = earliest_free(x, y, T);
        }
    }
    return T;
}

ll dist[2001][2001];
int dx[] = {0, 0, 1, -1};
int dy[] = {1, -1, 0, 0};

int main(){
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    cin >> N >> M;
    for(int i = 1; i <= N; i++){
        cin >> grid[i];
        grid[i] = " " + grid[i]; // FIX: pad with 1 space so grid[i][j] is 1-indexed
    }

    cin >> R;
    for(int i = 0; i < R; i++){
        int x, y; ll s, t;
        cin >> x >> y >> s >> t;
        courses[x][y].push_back({s, t});
    }

    for(int i = 1; i <= N; i++)
        for(int j = 1; j <= M; j++)
            sort(courses[i][j].begin(), courses[i][j].end());

    for(int i = 1; i <= N; i++)
        for(int j = 1; j <= M; j++)
            dist[i][j] = LLONG_MAX;

    if(grid[1][1] == '#') { cout << -1; return 0; }

    dist[1][1] = 0;
    priority_queue<State, vector<State>, greater<State>> pq;
    pq.push({0, 1, 1});

    while(!pq.empty()){
        auto [d, x, y] = pq.top(); pq.pop();

        if(d > dist[x][y]) continue;
        if(x == N && y == M) { cout << d; return 0; }

        for(int dir = 0; dir < 4; dir++){
            int nx = x + dx[dir];
            int ny = y + dy[dir];
            if(nx < 1 || nx > N || ny < 1 || ny > M) continue;
            if(grid[nx][ny] == '#') continue;

            ll arrive = d + 1;
            ll free_t = earliest_free(nx, ny, arrive);

            if(free_t < dist[nx][ny]){
                dist[nx][ny] = free_t;
                pq.push({free_t, nx, ny});
            }
        }
    }

    cout << (dist[N][M] == LLONG_MAX ? -1 : dist[N][M]);
    return 0;
}
