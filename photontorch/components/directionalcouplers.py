"""
# Directional Couplers

Directional Couplers are 4-port components coupling two waveguides together.

"""

#############
## Imports ##
#############

## Torch
import torch

## Other
import numpy as np

## Relative
from .component import Component
from .waveguides import Waveguide
from ..torch_ext.nn import BoundedParameter
from ..environment import current_environment


#########################
## Directional Coupler ##
#########################


class DirectionalCoupler(Component):
    r""" A directional coupler is a memory-less component with 4 ports.

    A directional coupler has one trainable parameter: the squared coupling coupling.

    Terms:
       3        2
        \______/
        /------\
       0        1

    Note:
        a directional coupler introduces no delays (for now)
    """

    num_ports = 4

    def __init__(self, coupling=0.5, trainable=True, name=None):
        """
        Args:
            coupling: float = 0.5: power coupling of the directional coupler (between 0
                and 1)
            trainable: bool = True: makes the coupling trainable
            name: str = None: the name of the component (default: lowercase classname)
        """
        super(DirectionalCoupler, self).__init__(name=name)

        self.coupling = BoundedParameter(
            data=torch.tensor(coupling, device=self.device),
            bounds=(0, 1),
            requires_grad=trainable,
        )

    def get_S(self):
        ones = torch.ones((self.env.num_wavelengths, 1, 1), device=self.device)
        t = ((1 - self.coupling) ** 0.5) * ones
        k = (self.coupling ** 0.5) * ones

        rS = t * torch.tensor(
            [[[0, 1, 0, 0], [1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]]],
            dtype=t.dtype,
            device=self.device,
        )
        iS = k * torch.tensor(
            [[[0, 0, 1, 0], [0, 0, 0, 1], [1, 0, 0, 0], [0, 1, 0, 0]]],
            dtype=k.dtype,
            device=self.device,
        )
        return torch.stack([rS, iS])


#####################################
## Directional Coupler with length ##
#####################################
class DirectionalCouplerWithLength(Component):
    r""" A directional coupler with length is a memory-containing component with 4 ports.

    It is merely a holder of a directional coupler and a waveguide, and combines both
    in a 4-port component.

    Terms:
        3        2
        \______/
        /------\
        0        1

    Note:
        This version of a directional coupler is prefered over a wg-wg-wg-wg-dc network
        becuase it only has 4 ports in stead of 12.
    """

    num_ports = 4

    def __init__(self, dc=None, wg=None, name=None):
        """
        Args:
            dc: DirectionalCoupler = None: directional coupler to add a length to
            wg: Waveguide = None: the waveguide containing the phase and delay information
                of the directional coupler.
            name: str = None: the name of the component (default: lowercase classname)
        """
        super(DirectionalCouplerWithLength, self).__init__(name=name)
        self.wg = wg if wg is not None else Waveguide()
        self.dc = dc if dc is not None else DirectionalCoupler()

    @property
    def coupling(self):
        """ Get the coupling of the directionalcoupler """
        return self.dc.coupling

    @property
    def phase(self):
        """ Get the phase introduced by the directional coupler """
        return self.wg.phase

    def initialize(self):
        self.wg.initialize()
        self.dc.initialize()
        Component.initialize(self)
        return self

    def get_delays(self):
        return torch.cat((self.wg.delays, self.wg.delays))

    def get_S(self):
        k = self.dc.coupling ** 0.5  # coupling
        t = (1 - self.dc.coupling) ** 0.5  # Transmission

        # Helper matrices
        S = self.wg.get_S()
        rS_wg_t = S[0] * t
        iS_wg_k = S[1] * k
        iS_wg_t = S[1] * t
        rS_wg_k = S[0] * k

        # S matrix
        S = torch.zeros((2, self.env.num_wavelengths, 4, 4), device=self.device)

        # Real part
        S[0, :, :2, :2] = rS_wg_t  # Transmission from i < - > j
        S[0, :, 2:, 2:] = rS_wg_t  # Transmission from k < - > l
        S[0, :, ::2, ::2] = -iS_wg_k
        S[0, :, 1::2, 1::2] = -iS_wg_k

        # Imag Part
        S[1, :, :2, :2] = iS_wg_t  # Transmission from i < - > j
        S[1, :, 2:, 2:] = iS_wg_t  # Transmission from k < - > l
        S[1, :, ::2, ::2] = rS_wg_k
        S[1, :, 1::2, 1::2] = rS_wg_k

        # Return
        return S


class RealisticDirectionalCoupler(Component):
    r""" A directional coupler is a memory-less component with 4 ports.

    Terms:
        3       2
        \______/
        /------\
        0       1

    Notes:
     - This directional coupler introduces no delays (for now)
     - This directional coupler is not trainable (for now)

    """

    num_ports = 4

    def __init__(
        self,
        length=12.8e-6,
        k0=0.2332,
        n0=0.0208,
        de1_k0=1.2435,
        de1_n0=0.1169,
        de2_k0=5.3022,
        de2_n0=0.4821,
        wl0=1.55e-6,
        name=None,
    ):
        """
        Args:
            length: float = 12.8e-6: the length
            k0: float = 0.2332: the bend coupling
            n0: float = 0.0208: effective index difference between even and odd mode
            de1_k0: float = 1.2435: first derivative of k0 w.r.t. wavelength
            de1_n0: float = 0.1169: first derivative of n0 w.r.t. wavelength
            de2_k0: float = 5.3022: second derivative of k0 w.r.t. wavelength
            de2_n0: float = 0.4821: second derivative of n0 w.r.t. wavelength
            wl0: float = 1.55e-6: the center wavelength for which the parameters are
                defined
            name: str = None: the name of the component (default: lowercase classname)

        Note:
            The default parameters are based on a directional coupler with
             - bend radius : 5um
             - adiabatic angle : 10 degrees
             - gap distance : 250 nm
        """

        super(RealisticDirectionalCoupler, self).__init__(name=name)
        self.length = length
        self.k0 = k0
        self.de1_k0 = de1_k0
        self.de2_k0 = de2_k0
        self.n0 = n0
        self.de1_n0 = de1_n0
        self.de2_n0 = de2_n0
        self.wl0 = wl0

    def get_S(self):
        wl = torch.tensor(self.env.wavelength, dtype=torch.float64, device=self.device)
        dwl = wl - self.wl0
        dn = self.n0 + self.de1_n0 * dwl + 0.5 * self.de2_n0 * dwl ** 2
        kappa0 = self.k0 + self.de1_k0 * dwl + 0.5 * self.de2_k0 * dwl ** 2
        kappa1 = np.pi * dn / wl

        dtype = torch.get_default_dtype()
        tau = torch.cos(kappa0 + kappa1 * self.length).to(dtype)[:, None, None]
        kappa = -torch.sin(kappa0 + kappa1 * self.length).to(dtype)[:, None, None]

        rS = tau * torch.tensor(
            [[[0, 1, 0, 0], [1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]]],
            dtype=dtype,
            device=self.device,
        )
        iS = kappa * torch.tensor(
            [[[0, 0, 1, 0], [0, 0, 0, 1], [1, 0, 0, 0], [0, 1, 0, 0]]],
            dtype=dtype,
            device=self.device,
        )
        return torch.stack([rS, iS])
