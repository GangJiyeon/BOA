#pragma once
#include <math.h>

// Diagnostic instantaneous score. The app/server compute the FINAL score from
// the fixed 3-second window's terminal median, using the same mapping.
namespace BoaMoisture60 {
inline int scoreFromResponse(double response) {
  if (!isfinite(response) || response < 0 || response > 100) return -1;
  const double nearest = round(response);
  if (fabs(response - nearest) < 1e-9) response = nearest;
  if (response == 100) return 60;
  const int breaks[] = {0,13,23,28,40,46,100};
  for (int band=0; band<6; ++band) {
    if (response < breaks[band+1]) {
      int within = int(floor(10*sqrt((response-breaks[band])/(breaks[band+1]-breaks[band]))));
      if (within > 9) within = 9;
      return 10*band+within;
    }
  }
  return -1;
}
inline int levelFromScore(int score) {
  if (score<0 || score>60) return -1;
  return score==60 ? 6 : score/10+1;
}
inline int instantaneousScore(unsigned baseline, unsigned count, unsigned divider) {
  if ((divider!=11 && divider!=22 && divider!=44) || !count || count>=baseline || baseline>4095) return -1;
  const double air=(baseline+170.0)*11/divider-170;
  const double contact=(count+170.0)*11/divider-170;
  if (air<=0 || contact<0) return -1;
  return scoreFromResponse(100*(air-contact)/air);
}
}
