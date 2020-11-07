'''Tensorflow implementations of encoder models'''

import tensorflow as tf
import tensorflow.keras as keras
from tensorflow.keras import backend as K
from tensorflow.keras.regularizers import l1_l2
import tensorflow.keras.layers as layers
import tensorflow.keras.losses as losses

import tensorflow_probability as tfp
tfpl = tfp.layers
tfd = tfp.distributions
tfd = tfp.bijectors

from .activations import clipped_softplus, clipped_exp
from .layers import ColwiseMult, DenseStack


class Encoder(keras.Model):
    '''Classical encoder model'''
    def __init__(
        self,
        latent_dim = 50,
        name='encoder',
        dropout_rate = 0.1,
        batchnorm = True,
        l1 = 0.,
        l2 = 0.,
        hidden_units = [128, 128],
        activation = 'leaky_relu',
        initializer = 'glorot_normal',
        **kwargs
    ):
        super().__init__(name=name, **kwargs)
        self.latent_dim = latent_dim
        self.dropout_rate = dropout_rate
        self.batchnorm =  batchnorm
        self.l1 = l1
        self.l2 = l2
        self.activation = activation
        self.hidden_units =  hidden_units
        self.initializer = keras.initializers.get(initializer)

        # Define components
        self.dense_stack = DenseStack(
            name = self.name,
            dropout_rate = self.dropout_rate,
            batchnorm = self.batchnorm,
            l1 = self.l1,
            l2 = self.l2,
            activation = self.activation,
            initializer = self.initializer,
            hidden_units = self.hidden_units
        )
        self.final_layer = layers.Dense(
            self.latent_dim, name = 'encoder_final',
            kernel_initializer = self.initializer
        )
        self.final_act = layers.Activation('linear', name='encoder_final_activation')

    def call(self, inputs):
        '''Full forward pass through model'''
        h = self.dense_stack(inputs)
        h = self.final_layer(h)
        outputs = self.final_act(h)
        return outputs


class VariationalEncoder(Encoder):
    '''Variational encoder'''
    def __init__(
        self,
        kld_weight = 1e-5,
        prior = 'normal',
        iaf_units = [128, 128],
        **kwargs
    ):
        super().__init__(**kwargs)
        self.kld_weight = kld_weight
        self.prior = prior
        self.iaf_units = iaf_units

        # Define components
        self.mu_sigma = layers.Dense(
            tfpl.MultivariateNormalTriL.params_size(self.latent_dim),
            name = 'encoder_mu_sigma',
            kernel_initializer = self.initializer,
            kernel_regularizer = l1_l2(self.l1, self.l2)
        )

        if self.prior == 'normal':
            # Independent() reinterprets each latent_dim as an independent distribution
            self.prior_dist = tfd.Independent(
                tfd.Normal(loc=tf.zeros(self.latent_dim), scale=1.),
                reinterpreted_batch_ndims = 1
            )
        elif self.prior == 'iaf':
            self.prior_dist = tfd.TransformedDistribution(
                distribution = tfd.Normal(loc=tf.zeros(self.latent_dim), scale=1.),
                bijector = tfb.Invert(tfb.MaskedAutoregressiveFlow(
                    shift_and_log_scale_fn=tfb.AutoregressiveNetwork(
                        params=2, hidden_units=self.iaf_units))),
                event_shape = self.latent_dim
            )

        self.sampling = tfpl.MultivariateNormalTriL(
            self.latent_dim,
            activity_regularizer = tfpl.KLDivergenceRegularizer(
                self.prior_dist,
                weight = self.kld_weight
            )
        )

    def call(self, inputs):
        '''Full forward pass through model'''
        h = self.dense_stack(inputs)
        h = self.mu_sigma(h)
        outputs = self.sampling(h)
        return outputs
